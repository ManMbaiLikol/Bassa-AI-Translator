"""Peuple `bassa_word_normalized` sur toutes les entrées du dictionnaire.

Cette version est sûre et idempotente : pas de `yield_per` avec commit
intermédiaire (ce qui invalide le cursor). On charge les IDs en mémoire, puis
on UPDATE par batches.

Pour les doublons tonaux confirmés (~188 groupes : `boire → nyo` vs `nyó`),
on garde la forme tonale (plus informative) et on supprime la forme nue.

Usage :
    python scripts/populate_normalized.py            # peuple uniquement
    python scripts/populate_normalized.py --dedupe   # peuple + déduplique
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal
from backend.models.dictionary import DictionaryEntry
from backend.services.tonal import has_tones, strip_tones


def populate(db) -> int:
    """Calcule `bassa_word_normalized` pour toutes les entrées où il manque
    ou est obsolète. Renvoie le nombre de mises à jour effectuées."""
    print("Phase 1: population de bassa_word_normalized...")
    # On charge (id, bassa_word, bassa_word_normalized) en mémoire — ~95k tuples
    # ≈ quelques Mo, sans danger.
    rows = (
        db.query(
            DictionaryEntry.id,
            DictionaryEntry.bassa_word,
            DictionaryEntry.bassa_word_normalized,
        )
        .all()
    )
    print(f"  {len(rows):,} entrées chargées")

    # Calcul de la valeur cible et liste des updates à appliquer
    to_update: list[tuple[int, str]] = []
    for entry_id, bw, current in rows:
        target = strip_tones(bw or "").lower()
        if current != target:
            to_update.append((entry_id, target))

    print(f"  {len(to_update):,} entrées à mettre à jour")

    BATCH = 1000
    updated = 0
    for i in range(0, len(to_update), BATCH):
        chunk = to_update[i : i + BATCH]
        # bulk_update_mappings = INSERT-like multi-row UPDATE
        db.bulk_update_mappings(
            DictionaryEntry,
            [{"id": eid, "bassa_word_normalized": norm} for eid, norm in chunk],
        )
        db.commit()
        updated += len(chunk)
        if updated % 10000 == 0 or updated == len(to_update):
            print(f"    ... {updated:,}/{len(to_update):,}")

    print(f"Phase 1 terminée : {updated:,} entrées normalisées.\n")
    return updated


def dedupe_tonal(db) -> int:
    """Supprime les doublons stricts : même (source_language, source_word,
    bassa_word_normalized), formes `bassa_word` différentes dont au moins une
    a des marques tonales. Garde la forme tonale (plus informative)."""
    print("Phase 2: déduplication tonale...")
    rows = (
        db.query(
            DictionaryEntry.id,
            DictionaryEntry.source_language,
            DictionaryEntry.source_word,
            DictionaryEntry.bassa_word,
            DictionaryEntry.bassa_word_normalized,
            DictionaryEntry.is_verified,
        )
        .all()
    )

    groups: dict[tuple[str, str, str], list[tuple]] = defaultdict(list)
    for r in rows:
        key = (r.source_language, r.source_word.lower(), r.bassa_word_normalized or "")
        groups[key].append(r)

    to_delete: list[int] = []
    kept_tonal = 0

    for key, items in groups.items():
        if len(items) < 2:
            continue
        # On ne supprime QUE si au moins une entrée a des tons ET au moins une n'en a pas
        # (= vrai doublon tonal). On ne touche pas aux doublons "même forme exacte".
        tonal = [r for r in items if has_tones(r.bassa_word)]
        non_tonal = [r for r in items if not has_tones(r.bassa_word)]
        if not tonal or not non_tonal:
            continue
        # On garde toutes les formes tonales, on supprime les formes nues
        # qui sont strictement une version "stripped" d'une autre forme du groupe.
        tonal_stripped = {strip_tones(r.bassa_word).lower() for r in tonal}
        for r in non_tonal:
            if r.bassa_word.lower() in tonal_stripped:
                to_delete.append(r.id)
                kept_tonal += 1

    print(f"  {len(to_delete):,} entrées à supprimer (doublons tonaux purs)")

    if to_delete:
        BATCH = 500
        for i in range(0, len(to_delete), BATCH):
            chunk = to_delete[i : i + BATCH]
            db.query(DictionaryEntry).filter(
                DictionaryEntry.id.in_(chunk)
            ).delete(synchronize_session=False)
            db.commit()

    print(f"Phase 2 terminée : {len(to_delete):,} doublons tonaux supprimés.\n")
    return len(to_delete)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dedupe",
        action="store_true",
        help="Supprime aussi les doublons tonaux purs après normalisation",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        populate(db)
        if args.dedupe:
            dedupe_tonal(db)
        total = db.query(DictionaryEntry).count()
        print(f"Dictionnaire final : {total:,} entrées")
    finally:
        db.close()


if __name__ == "__main__":
    main()
