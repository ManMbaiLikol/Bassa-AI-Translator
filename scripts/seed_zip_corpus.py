"""Build corpus pairs from ZIP phrase list.

Reads backend/seed/zip_phrases_fr.json (225 French phrases from 'Phrases en Bassa.zip'),
translates each with the dictionary engine, and inserts into corpus_pairs.

Phrases with at least 50% of words found in the dictionary are inserted as
is_verified=False (pending human review).  Phrases already in the corpus are skipped.

Usage:
    python scripts/seed_zip_corpus.py [--dry-run]
"""
import argparse
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal
from backend.engine.dictionary_engine import DictionaryEngine
from backend.models.corpus import CorpusPair


MIN_CONFIDENCE = 0.4   # minimum engine confidence to include a pair


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    src = Path("backend/seed/zip_phrases_fr.json")
    if not src.exists():
        print("zip_phrases_fr.json not found — run extraction first.")
        sys.exit(1)

    with open(src, encoding="utf-8") as f:
        phrases = json.load(f)

    print(f"Loaded {len(phrases)} phrases")

    # Load dictionary engine
    db = SessionLocal()
    engine = DictionaryEngine()
    engine.reload(db)
    print(f"Dictionary loaded: {len(engine._cache.get('fr', {}))} FR words")

    # Build set of existing corpus source texts
    existing = {
        p.source_text.lower().strip()
        for p in db.query(CorpusPair).filter(CorpusPair.source_language == "fr").all()
    }
    print(f"Existing FR corpus pairs: {len(existing)}")

    added = skipped_dup = skipped_low = 0

    for item in phrases:
        fr_text = item["fr"].strip()
        if fr_text.lower() in existing:
            skipped_dup += 1
            continue

        result = engine.translate(fr_text, "fr")

        if result.confidence < MIN_CONFIDENCE:
            skipped_low += 1
            if args.dry_run:
                print(f"  LOW ({result.confidence:.2f}): {fr_text!r}")
            continue

        bassa_text = result.translated_text.strip()
        if not bassa_text or bassa_text == fr_text:
            skipped_low += 1
            continue

        if args.dry_run:
            print(f"  ADD ({result.confidence:.2f}): {fr_text!r}")
            print(f"         -> {bassa_text!r}")
        else:
            pair = CorpusPair(
                source_language="fr",
                source_text=fr_text,
                bassa_text=bassa_text,
                domain="conversation",
                source_reference="Phrases en Bassa.zip (auto-traduit, à vérifier)",
                is_verified=False,
            )
            db.add(pair)
            existing.add(fr_text.lower())

        added += 1

    if not args.dry_run:
        db.commit()
        print(f"\nAdded {added} corpus pairs")
    else:
        print(f"\nDRY RUN: would add {added} pairs")

    print(f"Skipped: {skipped_dup} duplicates, {skipped_low} low confidence")
    db.close()


if __name__ == "__main__":
    main()
