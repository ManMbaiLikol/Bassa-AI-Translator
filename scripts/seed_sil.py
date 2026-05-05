"""Import SIL BasaaHTMLDictionary.zip into the database.

The ZIP contains a Bassa → French/English/German dictionary by Dr. Pierre Emmanuel Njock (2005).
We reverse the direction: FR→Bassa, EN→Bassa, DE→Bassa entries.

Run: python scripts/seed_sil.py
"""
import io
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import BeautifulSoup

from backend.database import SessionLocal
from backend.models.dictionary import DictionaryEntry

ZIP_PATH = Path(__file__).resolve().parent.parent / "backend" / "seed" / "BasaaHTMLDictionary.zip"

ALPHA_FILES = [f"Dict/{c}.html" for c in "abcdefghijklmnoprstuvwyz"]

POS_MAP = {
    "n.": "noun",
    "v.": "verb",
    "prn.": "pronoun",
    "adj.": "adjective",
    "adv.": "adverb",
    "prep.": "preposition",
    "conj.": "conjunction",
    "loc.": "expression",
    "npro.": "proper noun",
    "int.": "interjection",
    "pron.": "pronoun",
    "num.": "numeral",
    "n.m.": "noun",
    "n.f.": "noun",
}
# POS values to skip entirely (not useful as dictionary entries)
POS_SKIP = {"alph.", "emph.", "voc.", "emph"}

_PARENS = re.compile(r"\(.*?\)", re.DOTALL)
_GENDER_FR = re.compile(r"\s+[nmf]{1,2}p?\s*$", re.IGNORECASE)
_GENDER_DE = re.compile(r"\s+[nmf]\s*$", re.IGNORECASE)
_ART_FR = re.compile(r"^(le |la |les |l'|un |une |des |du )", re.IGNORECASE)
_ART_EN = re.compile(r"^(the |a |an )", re.IGNORECASE)
_ART_DE = re.compile(r"^(der |die |das |ein |eine |einem |einer |des |dem |den )", re.IGNORECASE)

_SKIP_FR = ("se ", "faire ", '"', "\u00ab", "tout ", "tous ", "toute ",
            "celui ", "celle ", "ceux ", "dient ", "c'est ", "acte de ", "fait de ")
_SKIP_EN = ("used to", "refers to", "said of", "this is", "one who")
_SKIP_DE = ("dient ", "er,", "sie,", "es,", "jn ", "jm ")

NOTE = "SIL BasaaHTMLDictionary \u00a9 Dr. Pierre Emmanuel Njock 2005"


def extract_keywords(text: str, lang: str, max_words: int = 5, max_len: int = 60) -> list[str]:
    """Return usable translation keywords extracted from a SIL definition string."""
    if not text:
        return []
    results = []
    for part in text.split(";"):
        part = part.split(":")[0]
        part = _PARENS.sub("", part).strip()
        part = part.rstrip(".,;").strip()
        for sub in part.split(","):
            sub = sub.strip()
            if lang == "fr":
                sub = _GENDER_FR.sub("", sub).strip()
                sub = _ART_FR.sub("", sub).strip()
                if any(sub.lower().startswith(s) for s in _SKIP_FR):
                    continue
            elif lang == "en":
                sub = _ART_EN.sub("", sub).strip()
                if any(sub.lower().startswith(s) for s in _SKIP_EN):
                    continue
            elif lang == "de":
                sub = _GENDER_DE.sub("", sub).strip()
                sub = _ART_DE.sub("", sub).strip()
                if any(sub.lower().startswith(s) for s in _SKIP_DE):
                    continue
            sub = sub.rstrip(".,;").strip()
            if len(sub) < 2 or len(sub) > max_len:
                continue
            words = sub.split()
            if len(words) > max_words:
                continue
            # Skip multi-word entries that begin with uppercase (likely sentences)
            if len(words) > 1 and sub[0].isupper():
                continue
            results.append(sub.lower().strip())
    seen: set[str] = set()
    return [r for r in results if not (r in seen or seen.add(r))]  # type: ignore[func-returns-value]


def parse_zip() -> list[dict]:
    """Parse all alpha HTML files. Returns list of candidate {source_language, source_word,
    bassa_word, phonetic, category} dicts."""
    entries: list[dict] = []
    with zipfile.ZipFile(ZIP_PATH) as z:
        available = set(z.namelist())
        for fname in ALPHA_FILES:
            if fname not in available:
                continue
            with z.open(fname) as f:
                html = f.read().decode("utf-8", errors="replace")
            soup = BeautifulSoup(html, "html.parser")
            for div in soup.find_all("div", class_="lxDIV"):
                lx = div.find("span", class_="lx")
                ps = div.find("span", class_="ps")
                dn = div.find("span", class_="dn")   # French
                de = div.find("span", class_="de")   # English
                dr = div.find("span", class_="dr")   # German
                ph = div.find("span", class_="ph")   # Phonetics

                if not lx:
                    continue
                bassa_word = lx.get_text().strip()
                if not bassa_word:
                    continue

                ps_raw = ps.get_text().strip() if ps else ""
                if ps_raw in POS_SKIP:
                    continue
                category = POS_MAP.get(ps_raw)
                phonetic = ph.get_text().strip() if ph else None

                for lang, span in [("fr", dn), ("en", de), ("de", dr)]:
                    if not span:
                        continue
                    raw = span.get_text().strip()
                    for kw in extract_keywords(raw, lang):
                        entries.append({
                            "source_language": lang,
                            "source_word": kw,
                            "bassa_word": bassa_word,
                            "phonetic": phonetic,
                            "category": category,
                        })
    return entries


def run(db, entries: list[dict]) -> tuple[int, int]:
    """Bulk-insert entries not already in the DB. Returns (added, skipped)."""
    existing = {
        (e.source_language, e.source_word.lower(), e.bassa_word.lower())
        for e in db.query(
            DictionaryEntry.source_language,
            DictionaryEntry.source_word,
            DictionaryEntry.bassa_word,
        ).all()
    }
    added = skipped = 0
    batch: list[DictionaryEntry] = []
    for item in entries:
        key = (item["source_language"], item["source_word"].lower(), item["bassa_word"].lower())
        if key in existing:
            skipped += 1
            continue
        existing.add(key)
        batch.append(
            DictionaryEntry(
                source_language=item["source_language"],
                source_word=item["source_word"],
                bassa_word=item["bassa_word"],
                phonetic=item.get("phonetic"),
                category=item.get("category"),
                notes=NOTE,
                is_verified=True,
            )
        )
        added += 1
        if len(batch) >= 500:
            db.bulk_save_objects(batch)
            db.commit()
            batch = []
    if batch:
        db.bulk_save_objects(batch)
        db.commit()
    return added, skipped


def main() -> None:
    print("=== SIL BasaaHTMLDictionary Importer ===")
    print(f"ZIP: {ZIP_PATH}\n")

    print("Parsing HTML files...")
    entries = parse_zip()
    lang_counts = Counter(e["source_language"] for e in entries)
    print(f"  Extracted {len(entries)} candidate entries")
    for lang, count in sorted(lang_counts.items()):
        print(f"    {lang.upper()}: {count}")

    db = SessionLocal()
    try:
        print("\nInserting (deduplication against existing DB)...")
        added, skipped = run(db, entries)
        print(f"  {added} added, {skipped} already existed")

        total = db.query(DictionaryEntry).count()
        fr = db.query(DictionaryEntry).filter(DictionaryEntry.source_language == "fr").count()
        en = db.query(DictionaryEntry).filter(DictionaryEntry.source_language == "en").count()
        de = db.query(DictionaryEntry).filter(DictionaryEntry.source_language == "de").count()
        print(f"\nDB totals: FR={fr}, EN={en}, DE={de}, TOTAL={total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
