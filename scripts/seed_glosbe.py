"""Import Glosbe-scraped entries into MySQL, skipping duplicates.

Run after scrape_glosbe.py:
    python scripts/seed_glosbe.py [--file backend/seed/glosbe_dictionary.json]
"""
import argparse
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal
from backend.models.dictionary import DictionaryEntry


def main():
    parser = argparse.ArgumentParser(description="Seed Glosbe entries into MySQL")
    parser.add_argument("--file", default="backend/seed/glosbe_dictionary.json")
    args = parser.parse_args()

    src = Path(args.file)
    if not src.exists():
        print(f"File not found: {src}")
        sys.exit(1)

    with open(src, "r", encoding="utf-8") as f:
        entries = json.load(f)

    db = SessionLocal()
    try:
        existing = {
            (e.source_language, e.source_word.lower())
            for e in db.query(DictionaryEntry).all()
        }

        added = skipped = 0
        for item in entries:
            lang = item["source_language"]
            word = item["source_word"].lower().strip()
            bassa = item["bassa_word"].strip()

            if not word or not bassa:
                continue
            if (lang, word) in existing:
                skipped += 1
                continue

            entry = DictionaryEntry(
                source_language=lang,
                source_word=word,
                bassa_word=bassa,
                category=item.get("category", ""),
                notes=item.get("notes", "Glosbe scrape"),
                is_verified=False,
            )
            db.add(entry)
            existing.add((lang, word))
            added += 1

        db.commit()
        print(f"Imported {added} entries, skipped {skipped} duplicates.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
