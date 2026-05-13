"""Import webonary_dictionary.json into the database.

Each Basaa entry becomes multiple DictionaryEntry rows (one per language/sense),
plus DictionaryExample rows for examples.

Languages supported: fr (French), en (English), de (German).
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal
from backend.models.dictionary import DictionaryEntry, DictionaryExample

SEED_FILE = Path(__file__).resolve().parent.parent / "backend" / "seed" / "webonary_dictionary.json"

LANG_KEYS = ["fr", "en", "de"]


def seed_webonary(clear_existing=False):
    if not SEED_FILE.exists():
        print(f"File not found: {SEED_FILE}")
        print("Run scripts/scrape_webonary.py first.")
        return

    with open(SEED_FILE, encoding="utf-8") as f:
        entries = json.load(f)
    print(f"Loaded {len(entries)} Basaa entries from webonary_dictionary.json")

    db = SessionLocal()
    try:
        if clear_existing:
            deleted = db.query(DictionaryEntry).filter(
                DictionaryEntry.notes.like("Webonary%")
            ).count()
            db.query(DictionaryExample).filter(
                DictionaryExample.entry_id.in_(
                    db.query(DictionaryEntry.id).filter(
                        DictionaryEntry.notes.like("Webonary%")
                    )
                )
            ).delete(synchronize_session=False)
            db.query(DictionaryEntry).filter(
                DictionaryEntry.notes.like("Webonary%")
            ).delete(synchronize_session=False)
            db.commit()
            print(f"Cleared {deleted} existing Webonary entries.")

        # Build set of existing (lang, source_word, bassa_word) to skip duplicates.
        # Keying by bassa_word too preserves multiple Basaa variants for the same
        # source word (e.g. "boire → nyo" AND "boire → nyó").
        existing = set()
        for e in db.query(
            DictionaryEntry.source_language,
            DictionaryEntry.source_word,
            DictionaryEntry.bassa_word,
        ).all():
            existing.add((e.source_language, e.source_word.lower(), e.bassa_word.lower()))

        added_entries = 0
        added_examples = 0
        skipped = 0

        for item in entries:
            bassa_word = item["bassa_word"].strip()
            if not bassa_word:
                continue

            category = item.get("category", "")
            plural = item.get("plural", "")
            senses = item.get("senses", [])

            for i, sense in enumerate(senses, start=1):
                sense_note = f"Webonary sens {i}" if len(senses) > 1 else "Webonary"

                for lang in LANG_KEYS:
                    translation = sense.get(lang, "").strip()
                    if not translation:
                        continue
                    # Some definitions start with grammatical markers like "v " or "s " — keep as-is
                    key = (lang, translation.lower(), bassa_word.lower())
                    if key in existing:
                        skipped += 1
                        continue

                    entry = DictionaryEntry(
                        source_language=lang,
                        source_word=translation[:191],
                        bassa_word=bassa_word[:500],
                        category=category,
                        plural_form=plural if lang == "fr" else "",
                        notes=sense_note,
                        is_verified=True,  # webonary is a curated source
                    )
                    db.add(entry)
                    db.flush()  # get entry.id for FK

                    existing.add(key)
                    added_entries += 1

                    # Add example sentence (only on the first language to avoid duplication)
                    if lang == "fr" and sense.get("example_bassa"):
                        ex = DictionaryExample(
                            entry_id=entry.id,
                            source_sentence=sense.get("example_fr", ""),
                            bassa_sentence=sense["example_bassa"],
                        )
                        db.add(ex)
                        added_examples += 1

        db.commit()
        print(f"Added {added_entries} dictionary entries ({skipped} skipped as duplicates)")
        print(f"Added {added_examples} example sentences")

    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Seed Webonary dictionary into DB")
    parser.add_argument("--clear", action="store_true",
                        help="Remove existing Webonary entries before importing")
    args = parser.parse_args()

    print("=== Seeding Webonary dictionary ===")
    seed_webonary(clear_existing=args.clear)
    print("=== Done! ===")
