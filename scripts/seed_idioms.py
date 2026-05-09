"""Seed curated French-Bassa idiomatic expressions into the dictionary.

These are verified, hand-curated expressions — stored as is_verified=True.
They cover greetings, courtesy formulas, common situations, and set phrases
that cannot be composed word-by-word by the regular translation engine.

Usage:
    python scripts/seed_idioms.py [--dry-run]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal
from backend.models.dictionary import DictionaryEntry

SEED_FILE = Path(__file__).resolve().parent.parent / "backend" / "seed" / "idioms_fr_bassa.json"


def seed(db, dry_run: bool = False) -> tuple[int, int]:
    with open(SEED_FILE, encoding="utf-8") as f:
        entries = json.load(f)

    existing = {
        e.source_word.lower().strip()
        for e in db.query(DictionaryEntry).filter(DictionaryEntry.source_language == "fr").all()
    }

    added = 0
    skipped = 0

    for item in entries:
        word = item["source_word"].lower().strip()
        bassa = item["bassa_word"].strip()

        if word in existing:
            skipped += 1
            continue

        if not dry_run:
            db.add(DictionaryEntry(
                source_language = "fr",
                source_word     = word,
                bassa_word      = bassa,
                category        = item.get("category", "expression"),
                is_verified     = True,
                notes           = item.get("notes", "Expression idiomatique (curated)"),
            ))
        existing.add(word)
        added += 1

    if not dry_run:
        db.commit()

    return added, skipped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Ne pas écrire en base")
    args = parser.parse_args()

    print("=== Import expressions idiomatiques FR->Bassa ===")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'ECRITURE EN BASE'}")
    print(f"  Source: {SEED_FILE.name}")

    db = SessionLocal()
    try:
        added, skipped = seed(db, dry_run=args.dry_run)
        action = "a ajouter" if args.dry_run else "ajoutees"
        print(f"\n  {added} expressions {action}")
        print(f"  {skipped} doublons ignores")

        if not args.dry_run and added > 0:
            total = db.query(DictionaryEntry).count()
            print(f"  Total dictionnaire: {total} entrees")

    finally:
        db.close()

    print("\n=== Termine! ===")


if __name__ == "__main__":
    main()
