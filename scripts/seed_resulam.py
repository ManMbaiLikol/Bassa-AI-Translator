"""Import Resulam 500-word list + PDF dictionary entries into MySQL.

Usage:
    python scripts/seed_resulam.py
"""
import io, sys, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parent.parent.__str__())

from backend.database import SessionLocal
from backend.models.dictionary import DictionaryEntry, DictionaryExample

SEED_DIR = __import__("pathlib").Path("backend/seed")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_SKIP_FR = {"le", "la", "les", "un", "une", "des", "du", "l", "d"}

def looks_french(text: str) -> bool:
    """Heuristic: return True if text looks like French noise (not a real word)."""
    low = text.lower().strip()
    # Contains spaces and starts with French article
    if re.match(r"^(le |la |les |un |une |des |du |l')", low):
        return True
    # All uppercase (likely a title/header)
    if text.isupper() and len(text) > 4:
        return True
    # Contains parenthetical grammar code as first chars
    if re.match(r"^\([a-z.]+\)", low):
        return True
    return False


def clean_bassa(bassa: str) -> str:
    """Clean up Bassa translation text."""
    # Remove trailing punctuation
    bassa = bassa.strip().rstrip(".,;:!?")
    # Collapse whitespace
    bassa = re.sub(r"\s+", " ", bassa).strip()
    return bassa


def clean_french(fr: str) -> str:
    """Lowercase + normalize French source word."""
    fr = fr.lower().strip().lstrip("'")
    # Remove gender markers at end: "(n.m.)", "(v.)", etc.
    fr = re.sub(r"\s*\([^)]+\)\s*$", "", fr).strip()
    return fr


# ---------------------------------------------------------------------------
# Import Resulam entries (100 high-quality numbered entries)
# ---------------------------------------------------------------------------
def seed_resulam(db, existing: set) -> int:
    src = SEED_DIR / "resulam_500.json"
    if not src.exists():
        print("resulam_500.json not found")
        return 0
    with open(src, encoding="utf-8") as f:
        items = json.load(f)

    added = 0
    for item in items:
        fr_raw = item["fr"]
        bassa = clean_bassa(item["bassa"])

        # Strip determiners from FR phrase to get the core word
        # "La tête" → "tête", "Mon frère" → keep as phrase
        fr = clean_french(fr_raw)
        # Also try stripping leading article
        fr_stripped = re.sub(r"^(le |la |les |un |une |des |du |l'|mon |ma |mes )", "", fr).strip()

        for word in set([fr, fr_stripped]):
            if not word or len(word) < 2:
                continue
            key = ("fr", word)
            if key in existing:
                continue
            entry = DictionaryEntry(
                source_language="fr",
                source_word=word,
                bassa_word=bassa,
                category="",
                notes=f"Resulam 500 mots (Pr. Bitjaa Kody) #{item['num']}",
                is_verified=True,
            )
            db.add(entry)
            existing.add(key)
            added += 1

    return added


# ---------------------------------------------------------------------------
# Import PDF dictionary entries
# ---------------------------------------------------------------------------
def seed_pdf(db, existing: set) -> int:
    src = SEED_DIR / "pdf_dictionary.json"
    if not src.exists():
        print("pdf_dictionary.json not found")
        return 0
    with open(src, encoding="utf-8") as f:
        items = json.load(f)

    added = 0
    for item in items:
        fr = clean_french(item.get("source_word", ""))
        bassa = clean_bassa(item.get("bassa_word", ""))

        if not fr or not bassa or len(fr) < 2 or len(bassa) < 1:
            continue
        # Skip garbled entries (Bassa contains French words)
        if looks_french(bassa):
            continue
        # Skip if bassa_word is identical to source_word (no translation)
        if bassa.lower() == fr.lower():
            continue
        # Skip if source_word has digits (page artifacts)
        if re.search(r"\d", fr):
            continue
        # Skip multi-word source that contains grammar jargon
        if re.search(r"\b(n\.m|n\.f|v\.|adj\.|adv\.|loc\.)", fr):
            continue

        key = ("fr", fr)
        if key in existing:
            continue

        entry = DictionaryEntry(
            source_language="fr",
            source_word=fr,
            bassa_word=bassa,
            category=item.get("category", ""),
            notes=item.get("notes", "PDF FR-Bassa Harmattan 2007"),
            is_verified=False,  # needs human review (OCR artifacts possible)
        )
        db.add(entry)
        existing.add(key)
        added += 1

    return added


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    db = SessionLocal()
    try:
        existing = {
            (e.source_language, e.source_word.lower())
            for e in db.query(DictionaryEntry).all()
        }
        print(f"Existing entries: {len(existing)}")

        print("\n--- Resulam 500 ---")
        r_added = seed_resulam(db, existing)
        print(f"  Added: {r_added}")

        print("\n--- PDF Dictionary ---")
        p_added = seed_pdf(db, existing)
        print(f"  Added: {p_added}")

        db.commit()
        total = r_added + p_added
        print(f"\nTotal added: {total}")
        print(f"New DB size: ~{len(existing)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
