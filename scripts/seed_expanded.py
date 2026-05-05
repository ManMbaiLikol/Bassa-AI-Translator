"""Import expanded dictionary entries into the database."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal
from backend.models.dictionary import DictionaryEntry

SEED_DIR = Path(__file__).resolve().parent.parent / "backend" / "seed"


def seed_expanded():
    """Import expanded dictionary entries, skipping duplicates."""
    dict_file = SEED_DIR / "expanded_dictionary.json"
    if not dict_file.exists():
        print("No expanded_dictionary.json found.")
        return

    db = SessionLocal()
    try:
        with open(dict_file, 'r', encoding='utf-8') as f:
            entries = json.load(f)

        # Get existing words to avoid duplicates (per language)
        existing = set()
        for e in db.query(DictionaryEntry).all():
            existing.add((e.source_language, e.source_word.lower()))

        added = 0
        skipped = 0
        for e in entries:
            lang = e["source_language"]
            word = e["source_word"].lower().strip()
            bassa = e["bassa_word"].strip()

            key = (lang, word)
            if key in existing:
                skipped += 1
                continue

            if len(word) < 1 or len(bassa) < 1:
                continue

            entry = DictionaryEntry(
                source_language=lang,
                source_word=word,
                bassa_word=bassa,
                category=e.get("category", ""),
                is_verified=False,
                notes=e.get("notes", "Expanded dictionary"),
            )
            db.add(entry)
            existing.add(key)
            added += 1

        db.commit()
        print(f"Imported {added} expanded dictionary entries (skipped {skipped} duplicates).")
    finally:
        db.close()


if __name__ == "__main__":
    print("=== Seeding expanded dictionary ===")
    seed_expanded()
    print("=== Done! ===")
