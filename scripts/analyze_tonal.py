"""Analyse l'état des marqueurs tonaux dans le dictionnaire Bassa.

Sortie : statistiques globales + détection des doublons tonaux.
"""
from __future__ import annotations

import sys
import unicodedata
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

from backend.database import SessionLocal
from backend.models.dictionary import DictionaryEntry


COMBINING_MARKS = {0x0300, 0x0301, 0x0302, 0x0303, 0x0304, 0x030C, 0x0308}


def strip_tones(text: str) -> str:
    """Décompose NFD puis retire les marques de tonalité courantes du Bassa."""
    if not text:
        return text
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if ord(c) not in COMBINING_MARKS)


def has_tones(text: str) -> bool:
    if not text:
        return False
    nfd = unicodedata.normalize("NFD", text)
    return any(ord(c) in COMBINING_MARKS for c in nfd)


def main() -> None:
    db = SessionLocal()
    try:
        total = db.query(DictionaryEntry).count()
        print(f"Total entries: {total:,}")

        with_tones = 0
        without_tones = 0
        by_source_lang: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        # bucket normalisé -> liste de (id, bassa_word)
        normalized_buckets: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)

        for entry in db.query(DictionaryEntry).yield_per(2000):
            bw = entry.bassa_word or ""
            if has_tones(bw):
                with_tones += 1
                by_source_lang[entry.source_language][0] += 1
            else:
                without_tones += 1
                by_source_lang[entry.source_language][1] += 1

            key = (entry.source_language, entry.source_word.lower(), strip_tones(bw).lower())
            normalized_buckets[(key[0], key[1] + "||" + key[2])].append((entry.id, bw))

        print(f"\nAvec tonalité   : {with_tones:>7,} ({100*with_tones/total:5.1f}%)")
        print(f"Sans tonalité   : {without_tones:>7,} ({100*without_tones/total:5.1f}%)")

        print("\nPar source_language :")
        for lang, (yes, no) in sorted(by_source_lang.items()):
            tot = yes + no
            pct = 100 * yes / tot if tot else 0
            print(f"  {lang}: avec={yes:>6,}  sans={no:>6,}  ({pct:4.1f}% tonal)")

        # Doublons tonaux : même (source_word, bassa_normalisé), formes bassa différentes
        duplicates: list[tuple[str, list[tuple[int, str]]]] = []
        for k, items in normalized_buckets.items():
            if len(items) < 2:
                continue
            forms = {bw for _, bw in items}
            if len(forms) >= 2:
                duplicates.append((k, items))

        print(f"\nDoublons tonaux détectés : {len(duplicates):,} groupes")
        print("Exemples (10 premiers) :")
        for key, items in duplicates[:10]:
            lang, rest = key.split(":", 1) if ":" in key else ("", key)
            print(f"  [{rest}]")
            for entry_id, bw in items:
                marker = "★" if has_tones(bw) else " "
                print(f"     {marker} #{entry_id}: {bw!r}")

        # Échantillons
        print("\nÉchantillon avec tonalité (10) :")
        sample_with = (
            db.query(DictionaryEntry)
            .filter(DictionaryEntry.source_language == "fr")
            .limit(5000)
            .all()
        )
        shown = 0
        for e in sample_with:
            if has_tones(e.bassa_word) and shown < 10:
                print(f"  {e.source_word:<20} -> {e.bassa_word}")
                shown += 1

        print("\nÉchantillon sans tonalité (10) :")
        shown = 0
        for e in sample_with:
            if not has_tones(e.bassa_word) and shown < 10:
                print(f"  {e.source_word:<20} -> {e.bassa_word}")
                shown += 1
    finally:
        db.close()


if __name__ == "__main__":
    main()
