"""Expand multi-word source_word entries into individual word entries.

The Webonary import stored full French/English/German glosses as source_word,
e.g. 'nourriture f, aliment m' → 'bìjɛk'.  This script splits those glosses
into individual words so the tokenizer can find them.

Safe to run multiple times: skips words already in the database.

Usage:
    python scripts/expand_definitions.py [--dry-run] [--lang fr]
"""

import argparse
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal
from backend.models.dictionary import DictionaryEntry

# ---------------------------------------------------------------------------
# Grammatical markers to strip from the end of words in definitions
# e.g.  "nourriture f" → "nourriture"
# ---------------------------------------------------------------------------
_GRAM_SUFFIXES = re.compile(
    r"\s+(?:f|m|fp|mp|fpl|mpl|pl|sg|vt|vi|adj|adv|pron|prép|prp|conj|n|v)\b\.?$",
    re.IGNORECASE,
)

# Words to skip even if they appear in a definition
_SKIP_WORDS = {
    # French articles / prepositions too short to be useful
    "le", "la", "les", "un", "une", "des", "du", "de", "d",
    "à", "au", "aux", "en", "et", "ou", "que", "qui", "se",
    # Noise from definitions
    "par", "pour", "avec", "dans", "sur", "sous",
    "ex", "cf", "pl", "sg", "voir", "var",
    # Single chars
    "f", "m", "n", "v",
}

# Min length of a word to be added
_MIN_WORD_LEN = 3


def split_definition(definition: str) -> list[str]:
    """Split a multi-word gloss into individual candidate source words."""
    # Split on comma, semicolon, slash, or pipe
    parts = re.split(r"[,;/|]", definition)
    words = []
    for part in parts:
        part = part.strip()
        # Strip trailing grammatical markers
        part = _GRAM_SUFFIXES.sub("", part).strip()
        # Strip leading articles / determiners
        part = re.sub(r"^(?:le|la|les|un|une|des|du|d[e'])\s+", "", part, flags=re.IGNORECASE).strip()
        # Strip parenthetical content
        part = re.sub(r"\([^)]*\)", "", part).strip()
        # Lowercase
        word = part.lower()
        # Keep only words that are purely alphabetic (with diacritics) and not too short
        if (
            len(word) >= _MIN_WORD_LEN
            and word not in _SKIP_WORDS
            and re.match(r"^[a-zà-ÿœæ'-]+$", word)
        ):
            words.append(word)
    return words


def main():
    parser = argparse.ArgumentParser(description="Expand multi-word definitions")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--lang", default="all", help="Language to process: fr, en, de, or all")
    args = parser.parse_args()

    langs = ["fr", "en", "de"] if args.lang == "all" else [args.lang]

    db = SessionLocal()
    try:
        # Build lookup of existing (lang, word) pairs
        print("Loading existing entries...")
        existing = {
            (e.source_language, e.source_word.lower())
            for e in db.query(DictionaryEntry).all()
        }
        print(f"  {len(existing)} existing entries loaded")

        total_added = 0
        total_skipped = 0

        for lang in langs:
            # Find entries with commas or semicolons in source_word
            multi_entries = (
                db.query(DictionaryEntry)
                .filter(
                    DictionaryEntry.source_language == lang,
                    DictionaryEntry.source_word.op("REGEXP")("[,;/]"),
                )
                .all()
            )
            print(f"\n[{lang}] {len(multi_entries)} multi-word entries to expand")

            added = skipped = 0
            for entry in multi_entries:
                words = split_definition(entry.source_word)
                for word in words:
                    key = (lang, word)
                    if key in existing:
                        skipped += 1
                        continue

                    if not args.dry_run:
                        new_entry = DictionaryEntry(
                            source_language=lang,
                            source_word=word,
                            bassa_word=entry.bassa_word,
                            category=entry.category,
                            notes=f"Expanded from: {entry.source_word[:80]}",
                            is_verified=False,
                        )
                        db.add(new_entry)

                    existing.add(key)
                    added += 1

                    if args.dry_run and added <= 20:
                        print(f"  WOULD ADD: [{lang}] {word!r} -> {entry.bassa_word!r}")

            total_added += added
            total_skipped += skipped
            print(f"  -> {added} new words, {skipped} already exist")

        if not args.dry_run:
            db.commit()
            print(f"\nCommitted {total_added} new entries ({total_skipped} skipped)")
        else:
            print(f"\nDRY RUN: would add {total_added} entries ({total_skipped} skipped)")

    finally:
        db.close()


if __name__ == "__main__":
    main()
