"""Import JW.org Bible corpus and dictionary into the database.

Run after: python scripts/scrape_bible_jw.py

Usage:
    python scripts/seed_bible_jw.py [--corpus bible_jw_corpus.json]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal
from backend.models.corpus import CorpusPair
from backend.models.dictionary import DictionaryEntry

SEED_DIR = Path(__file__).resolve().parent.parent / "backend" / "seed"


def seed_corpus(db, corpus_filename="bible_jw_corpus.json"):
    corpus_file = SEED_DIR / corpus_filename
    if not corpus_file.exists():
        print("bible_jw_corpus.json introuvable. Lance scrape_bible_jw.py d'abord.")
        return 0

    with open(corpus_file, encoding="utf-8") as f:
        pairs = json.load(f)

    existing = {
        (r.source_text[:50], r.bassa_text[:50])
        for r in db.query(CorpusPair).filter(CorpusPair.domain == "bible").all()
    }

    batch = []
    for p in pairs:
        fr  = p["source_text"].strip()
        bas = p["bassa_text"].strip()
        if len(fr) < 15 or len(bas) < 10:
            continue
        key = (fr[:50], bas[:50])
        if key in existing:
            continue
        batch.append(CorpusPair(
            source_language  = p["source_language"],
            source_text      = fr[:600],
            bassa_text       = bas[:600],
            domain           = "bible",
            source_reference = p.get("source_reference", ""),
            is_verified      = p.get("is_verified", False),
        ))
        existing.add(key)

    db.add_all(batch)
    db.commit()
    print(f"  Corpus: {len(batch)} nouvelles paires ajoutées")
    return len(batch)


def seed_dictionary(db, corpus_filename="bible_jw_corpus.json"):
    dict_stem = Path(corpus_filename).stem  # e.g. "bible_jw_ot_corpus"
    dict_file = SEED_DIR / (dict_stem.replace("_corpus", "_dictionary") + ".json")
    if not dict_file.exists():
        print("bible_jw_dictionary.json introuvable.")
        return 0

    with open(dict_file, encoding="utf-8") as f:
        entries = json.load(f)

    existing_words = {
        e.source_word.lower()
        for e in db.query(DictionaryEntry).filter(DictionaryEntry.source_language == "fr").all()
    }

    added = 0
    for e in entries:
        word  = e["source_word"].lower().strip()
        bassa = e["bassa_word"].strip()

        if word in existing_words:
            continue
        if len(word) < 3 or len(bassa) < 2:
            continue
        if not word[0].isalpha() or not bassa[0].isalpha():
            continue
        if e.get("count", 0) < 5:
            continue

        db.add(DictionaryEntry(
            source_language = "fr",
            source_word     = word,
            bassa_word      = bassa,
            is_verified     = False,
            notes           = f"Bible JW.org (count={e.get('count', 0)}, score={e.get('score', 0)})",
        ))
        existing_words.add(word)
        added += 1

    db.commit()
    print(f"  Dictionnaire: {added} nouvelles entrées ajoutées")
    return added


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default="bible_jw_corpus.json", help="Nom du fichier corpus dans backend/seed/")
    args = parser.parse_args()

    print(f"=== Import Bible JW.org ({args.corpus}) ===")
    db = SessionLocal()
    try:
        seed_corpus(db, args.corpus)
        seed_dictionary(db, args.corpus)
    finally:
        db.close()
    print("=== Terminé! ===")
