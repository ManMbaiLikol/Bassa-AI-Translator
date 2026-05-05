"""Import Bible corpus pairs and curated dictionary entries into the database."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal
from backend.models.corpus import CorpusPair
from backend.models.dictionary import DictionaryEntry

SEED_DIR = Path(__file__).resolve().parent.parent / "backend" / "seed"


def seed_corpus():
    """Import Bible corpus pairs."""
    corpus_file = SEED_DIR / "bible_corpus.json"
    if not corpus_file.exists():
        print("No bible_corpus.json found. Run extract_bible.py first.")
        return

    db = SessionLocal()
    try:
        existing = db.query(CorpusPair).filter(CorpusPair.domain == "bible").count()
        if existing > 0:
            print(f"Bible corpus already has {existing} entries. Skipping.")
            return

        with open(corpus_file, 'r', encoding='utf-8') as f:
            pairs = json.load(f)

        # Filter: keep only pairs where both texts are reasonable length
        good_pairs = []
        for p in pairs:
            fr = p["source_text"].strip()
            bs = p["bassa_text"].strip()
            # Skip very short or very long entries
            if len(fr) < 20 or len(bs) < 15:
                continue
            if len(fr) > 500 or len(bs) > 500:
                continue
            good_pairs.append(p)

        batch = []
        for p in good_pairs:
            batch.append(CorpusPair(
                source_language=p["source_language"],
                source_text=p["source_text"][:500],
                bassa_text=p["bassa_text"][:500],
                domain="bible",
                source_reference=p.get("source_reference", ""),
                is_verified=p.get("is_verified", False),
            ))

        db.add_all(batch)
        db.commit()
        print(f"Imported {len(batch)} Bible corpus pairs.")
    finally:
        db.close()


def seed_dictionary():
    """Import curated Bible dictionary entries.

    Only imports entries that pass quality filters.
    """
    dict_file = SEED_DIR / "bible_dictionary.json"
    if not dict_file.exists():
        print("No bible_dictionary.json found. Run extract_bible.py first.")
        return

    db = SessionLocal()
    try:
        with open(dict_file, 'r', encoding='utf-8') as f:
            entries = json.load(f)

        # Get existing words to avoid duplicates
        existing_words = {
            e.source_word.lower()
            for e in db.query(DictionaryEntry).filter(DictionaryEntry.source_language == "fr").all()
        }

        added = 0
        for e in entries:
            word = e["source_word"].lower().strip()
            bassa = e["bassa_word"].strip()

            # Quality filters
            if word in existing_words:
                continue
            if len(word) < 3 or len(bassa) < 2:
                continue
            # Skip partial words (likely PDF artifacts)
            if not word[0].isalpha() or not bassa[0].isalpha():
                continue
            # Skip words that look like fragments
            if word.startswith("ll") or word.startswith("rr"):
                continue
            # Skip if count too low
            if e.get("count", 0) < 10:
                continue

            entry = DictionaryEntry(
                source_language="fr",
                source_word=word,
                bassa_word=bassa,
                is_verified=False,
                notes=f"Extracted from Bible corpus (count={e.get('count', 0)})",
            )
            db.add(entry)
            existing_words.add(word)
            added += 1

        db.commit()
        print(f"Imported {added} Bible dictionary entries (filtered from {len(entries)}).")
    finally:
        db.close()


if __name__ == "__main__":
    print("=== Seeding Bible data into database ===")
    seed_corpus()
    seed_dictionary()
    print("=== Done! ===")
