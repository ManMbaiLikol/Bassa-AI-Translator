"""Seed all data into the database from JSON files.

Run once after alembic migrations on a fresh database.
Each step is idempotent: it skips data that already exists.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from passlib.context import CryptContext
from backend.database import SessionLocal
from backend.models.user import User, UserRole
from backend.models.dictionary import DictionaryEntry, DictionaryExample
from backend.models.corpus import CorpusPair
from backend.models.grammar import GrammaticalRule

SEED_DIR = Path(__file__).resolve().parent / "seed"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_existing(db) -> set:
    return {
        (e.source_language, e.source_word.lower())
        for e in db.query(DictionaryEntry.source_language, DictionaryEntry.source_word).all()
    }


def _clean_bassa(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().rstrip(".,;:!?")).strip()


def _clean_french(text: str) -> str:
    text = text.lower().strip().lstrip("'")
    return re.sub(r"\s*\([^)]+\)\s*$", "", text).strip()


# ---------------------------------------------------------------------------
# 1. Base dictionary (dictionary_seed.json)
# ---------------------------------------------------------------------------
def seed_base_dictionary(db, existing: set) -> int:
    src = SEED_DIR / "dictionary_seed.json"
    if not src.exists():
        print("  [SKIP] dictionary_seed.json not found")
        return 0

    with open(src, encoding="utf-8") as f:
        entries = json.load(f)

    added = 0
    for item in entries:
        examples_data = item.pop("examples", [])
        lang = item["source_language"]
        word = item["source_word"]
        key = (lang, word.lower())
        if key in existing:
            continue
        entry = DictionaryEntry(
            source_language=lang,
            source_word=word,
            bassa_word=item["bassa_word"],
            phonetic=item.get("phonetic"),
            category=item.get("category"),
            gender=item.get("gender"),
            plural_form=item.get("plural_form"),
            notes=item.get("notes"),
            is_verified=True,
        )
        db.add(entry)
        db.flush()
        existing.add(key)
        for ex in examples_data:
            db.add(DictionaryExample(
                entry_id=entry.id,
                source_sentence=ex["source_sentence"],
                bassa_sentence=ex["bassa_sentence"],
            ))
        added += 1

    db.commit()
    return added


# ---------------------------------------------------------------------------
# 2. Webonary dictionary (webonary_dictionary.json)
# ---------------------------------------------------------------------------
def seed_webonary(db, existing: set) -> int:
    src = SEED_DIR / "webonary_dictionary.json"
    if not src.exists():
        print("  [SKIP] webonary_dictionary.json not found")
        return 0

    with open(src, encoding="utf-8") as f:
        entries = json.load(f)

    added = added_ex = 0
    for item in entries:
        bassa_word = item.get("bassa_word", "").strip()
        if not bassa_word:
            continue
        category = item.get("category", "")
        plural = item.get("plural", "")
        senses = item.get("senses", [])

        for i, sense in enumerate(senses, start=1):
            note = f"Webonary sens {i}" if len(senses) > 1 else "Webonary"
            for lang in ("fr", "en", "de"):
                translation = sense.get(lang, "").strip()
                if not translation:
                    continue
                key = (lang, translation.lower())
                if key in existing:
                    continue
                entry = DictionaryEntry(
                    source_language=lang,
                    source_word=translation,
                    bassa_word=bassa_word,
                    category=category,
                    plural_form=plural if lang == "fr" else "",
                    notes=note,
                    is_verified=True,
                )
                db.add(entry)
                db.flush()
                existing.add(key)
                added += 1
                if lang == "fr" and sense.get("example_bassa"):
                    db.add(DictionaryExample(
                        entry_id=entry.id,
                        source_sentence=sense.get("example_fr", ""),
                        bassa_sentence=sense["example_bassa"],
                    ))
                    added_ex += 1

    db.commit()
    return added


# ---------------------------------------------------------------------------
# 3. Expanded dictionary (expanded_dictionary.json)
# ---------------------------------------------------------------------------
def seed_expanded(db, existing: set) -> int:
    src = SEED_DIR / "expanded_dictionary.json"
    if not src.exists():
        print("  [SKIP] expanded_dictionary.json not found")
        return 0

    with open(src, encoding="utf-8") as f:
        entries = json.load(f)

    added = 0
    for e in entries:
        lang = e["source_language"]
        word = e["source_word"].lower().strip()
        bassa = e["bassa_word"].strip()
        key = (lang, word)
        if key in existing or not word or not bassa:
            continue
        db.add(DictionaryEntry(
            source_language=lang,
            source_word=word,
            bassa_word=bassa,
            category=e.get("category", ""),
            is_verified=False,
            notes=e.get("notes", "Expanded dictionary"),
        ))
        existing.add(key)
        added += 1

    db.commit()
    return added


# ---------------------------------------------------------------------------
# 4. Resulam 500 + PDF dictionary (resulam_500.json + pdf_dictionary.json)
# ---------------------------------------------------------------------------
def seed_resulam(db, existing: set) -> int:
    src = SEED_DIR / "resulam_500.json"
    if not src.exists():
        print("  [SKIP] resulam_500.json not found")
        return 0

    with open(src, encoding="utf-8") as f:
        items = json.load(f)

    added = 0
    for item in items:
        bassa = _clean_bassa(item["bassa"])
        fr = _clean_french(item["fr"])
        fr_stripped = re.sub(r"^(le |la |les |un |une |des |du |l'|mon |ma |mes )", "", fr).strip()
        for word in set([fr, fr_stripped]):
            if not word or len(word) < 2:
                continue
            key = ("fr", word)
            if key in existing:
                continue
            db.add(DictionaryEntry(
                source_language="fr",
                source_word=word,
                bassa_word=bassa,
                notes=f"Resulam 500 mots (Pr. Bitjaa Kody) #{item['num']}",
                is_verified=True,
            ))
            existing.add(key)
            added += 1

    db.commit()
    return added


def seed_pdf(db, existing: set) -> int:
    src = SEED_DIR / "pdf_dictionary.json"
    if not src.exists():
        print("  [SKIP] pdf_dictionary.json not found")
        return 0

    with open(src, encoding="utf-8") as f:
        items = json.load(f)

    _LOOKS_FRENCH = re.compile(r"^(le |la |les |un |une |des |du |l')", re.I)

    added = 0
    for item in items:
        fr = _clean_french(item.get("source_word", ""))
        bassa = _clean_bassa(item.get("bassa_word", ""))
        if not fr or not bassa or len(fr) < 2:
            continue
        if _LOOKS_FRENCH.match(bassa) or bassa.lower() == fr.lower():
            continue
        if re.search(r"\d", fr):
            continue
        key = ("fr", fr)
        if key in existing:
            continue
        db.add(DictionaryEntry(
            source_language="fr",
            source_word=fr,
            bassa_word=bassa,
            category=item.get("category", ""),
            notes=item.get("notes", "PDF FR-Bassa Harmattan 2007"),
            is_verified=False,
        ))
        existing.add(key)
        added += 1

    db.commit()
    return added


# ---------------------------------------------------------------------------
# 5. Bible corpus + dictionary
# ---------------------------------------------------------------------------
def seed_bible_corpus(db) -> int:
    src = SEED_DIR / "bible_corpus.json"
    if not src.exists():
        print("  [SKIP] bible_corpus.json not found")
        return 0

    existing_count = db.query(CorpusPair).filter(CorpusPair.domain == "bible").count()
    if existing_count > 0:
        print(f"  [SKIP] Bible corpus already has {existing_count} entries")
        return 0

    with open(src, encoding="utf-8") as f:
        pairs = json.load(f)

    batch = []
    for p in pairs:
        fr = p["source_text"].strip()
        bs = p["bassa_text"].strip()
        if len(fr) < 20 or len(bs) < 15 or len(fr) > 500 or len(bs) > 500:
            continue
        batch.append(CorpusPair(
            source_language=p["source_language"],
            source_text=fr[:500],
            bassa_text=bs[:500],
            domain="bible",
            source_reference=p.get("source_reference", ""),
            is_verified=p.get("is_verified", False),
        ))

    db.add_all(batch)
    db.commit()
    return len(batch)


def seed_bible_dictionary(db, existing: set) -> int:
    src = SEED_DIR / "bible_dictionary.json"
    if not src.exists():
        print("  [SKIP] bible_dictionary.json not found")
        return 0

    with open(src, encoding="utf-8") as f:
        entries = json.load(f)

    added = 0
    for e in entries:
        word = e["source_word"].lower().strip()
        bassa = e["bassa_word"].strip()
        key = ("fr", word)
        if key in existing or len(word) < 3 or len(bassa) < 2:
            continue
        if not word[0].isalpha() or not bassa[0].isalpha():
            continue
        if e.get("count", 0) < 10:
            continue
        db.add(DictionaryEntry(
            source_language="fr",
            source_word=word,
            bassa_word=bassa,
            is_verified=False,
            notes=f"Extracted from Bible corpus (count={e.get('count', 0)})",
        ))
        existing.add(key)
        added += 1

    db.commit()
    return added


# ---------------------------------------------------------------------------
# 6. Admin user + grammar rules
# ---------------------------------------------------------------------------
def seed_admin(db) -> None:
    if db.query(User).filter(User.username == "admin").first():
        print("  [SKIP] Admin user already exists")
        return
    db.add(User(
        username="admin",
        email="admin@bassatranslator.local",
        hashed_password=pwd_context.hash("admin123"),
        role=UserRole.admin,
    ))
    db.commit()
    print("  Admin user created (admin / admin123).")


def seed_grammar_rules(db) -> None:
    if db.query(GrammaticalRule).count() > 0:
        print("  [SKIP] Grammar rules already exist")
        return
    rules = [
        GrammaticalRule(rule_name="FR subject-verb order", source_language="fr",
                        pattern="PRON VERB", transformation="PRON VERB", priority=10, is_active=True),
        GrammaticalRule(rule_name="FR negation ne...pas removal", source_language="fr",
                        pattern="ne VERB pas", transformation="VERB ga", priority=20, is_active=True),
        GrammaticalRule(rule_name="EN subject-verb order", source_language="en",
                        pattern="PRON VERB", transformation="PRON VERB", priority=10, is_active=True),
    ]
    db.add_all(rules)
    db.commit()
    print(f"  Added {len(rules)} grammar rules.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    print("=== BassaAI Translator — Database Seed ===")
    db = SessionLocal()
    try:
        existing = _load_existing(db)
        print(f"Existing dictionary entries: {len(existing)}")

        print("\n[1/8] Base dictionary...")
        n = seed_base_dictionary(db, existing)
        print(f"  Added {n} entries")

        print("\n[2/8] Webonary dictionary...")
        n = seed_webonary(db, existing)
        print(f"  Added {n} entries")

        print("\n[3/8] Expanded dictionary...")
        n = seed_expanded(db, existing)
        print(f"  Added {n} entries")

        print("\n[4/8] Resulam 500...")
        n = seed_resulam(db, existing)
        print(f"  Added {n} entries")

        print("\n[5/8] PDF dictionary...")
        n = seed_pdf(db, existing)
        print(f"  Added {n} entries")

        print("\n[6/8] Bible corpus...")
        n = seed_bible_corpus(db)
        print(f"  Added {n} corpus pairs")

        print("\n[7/8] Bible dictionary...")
        n = seed_bible_dictionary(db, existing)
        print(f"  Added {n} entries")

        print("\n[8/8] Admin user + grammar rules...")
        seed_admin(db)
        seed_grammar_rules(db)

        final = db.query(DictionaryEntry).count()
        print(f"\n=== Done! Total dictionary entries: {final} ===")
    finally:
        db.close()


if __name__ == "__main__":
    main()
