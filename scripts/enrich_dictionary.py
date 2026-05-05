"""Targeted dictionary enrichment: fix known errors and add missing common words.

Run: python scripts/enrich_dictionary.py
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal
from backend.models.dictionary import DictionaryEntry


# ---------------------------------------------------------------------------
# Corrections: entries that exist with a wrong Bassa translation
# ---------------------------------------------------------------------------
CORRECTIONS = [
    # avant: typo in DB (ibisu vs i bisu)
    {
        "source_language": "fr",
        "source_word": "avant",
        "old_bassa": "ibisu bi ngéda",
        "new_bassa": "i bisu bi ngéda",
        "reason": "correction orthographe : espace manquante avant 'bisu'",
    },
    # frère : la forme nyañgal est le terme générique pour 'frère/sœur' ;
    # la forme spécifique genrée est mǎnkéé nú mùnlóm — on la marque non-vérifiée
    # pour ne pas supprimer l'info, mais on ne la corrige pas ici.
]

# ---------------------------------------------------------------------------
# Additions: entries missing or needing a verified specific form
# ---------------------------------------------------------------------------
NEW_ENTRIES = [
    # --- Pronouns (formes correctes) ---
    {
        "source_language": "fr",
        "source_word": "moi",
        "bassa_word": "mè",
        "category": "pronoun",
        "notes": "Pronom tonique 1sg (ton bas : mè ≠ me sujet)",
    },
    {
        "source_language": "en",
        "source_word": "me",
        "bassa_word": "mè",
        "category": "pronoun",
        "notes": "Object pronoun 1sg",
    },
    # --- Time ---
    {
        "source_language": "fr",
        "source_word": "an",
        "bassa_word": "wî",
        "category": "noun",
        "notes": "an / année → wî ; ne pas confondre avec mbu (autre mot)",
    },
    # --- Family (formes genrées spécifiques) ---
    {
        "source_language": "fr",
        "source_word": "soeur",
        "bassa_word": "Mǎnkéé nú mùdàá",
        "category": "noun",
        "notes": "Sœur (féminin) ; cf. frère = Mǎnkéé nú mùnlóm ; nyañgal = frère/sœur générique",
    },
    {
        "source_language": "en",
        "source_word": "sister",
        "bassa_word": "Mǎnkéé nú mùdàá",
        "category": "noun",
        "notes": "Sister (female sibling) ; cf. brother = Mǎnkéé nú mùnlóm",
    },
    {
        "source_language": "en",
        "source_word": "brother",
        "bassa_word": "Mǎnkéé nú mùnlóm",
        "category": "noun",
        "notes": "Brother (male sibling) ; nyañgal = generic sibling",
    },
    # --- Sleep ---
    {
        "source_language": "fr",
        "source_word": "dormir",
        "bassa_word": "nangâl",
        "category": "verb",
        "notes": "Forme correcte confirmée ; nôgôl = variante/doublon",
    },
    # --- Prepositions ---
    {
        "source_language": "fr",
        "source_word": "avant",
        "bassa_word": "i bisu bi ngéda",
        "category": "preposition",
        "notes": "Avant (temporel/spatial)",
    },
    {
        "source_language": "fr",
        "source_word": "par",
        "bassa_word": "i",
        "category": "preposition",
        "notes": "Préposition 'par' ; forme courte (ini = forme longue)",
    },
    {
        "source_language": "fr",
        "source_word": "par",
        "bassa_word": "ini",
        "category": "preposition",
        "notes": "Préposition 'par' ; forme longue (i = forme courte)",
    },
    {
        "source_language": "fr",
        "source_word": "vers",
        "bassa_word": "nyô",
        "category": "preposition",
        "notes": "Vers (direction)",
    },
    {
        "source_language": "fr",
        "source_word": "derrière",
        "bassa_word": "i mbuss",
        "category": "preposition",
        "notes": "Derrière (position spatiale)",
    },
    # Équivalents anglais des prépositions
    {
        "source_language": "en",
        "source_word": "before",
        "bassa_word": "i bisu bi ngéda",
        "category": "preposition",
        "notes": "Before (temporal/spatial)",
    },
    {
        "source_language": "en",
        "source_word": "by",
        "bassa_word": "i",
        "category": "preposition",
        "notes": "By / through (short form) ; ini = long form",
    },
    {
        "source_language": "en",
        "source_word": "toward",
        "bassa_word": "nyô",
        "category": "preposition",
        "notes": "Toward / towards (direction)",
    },
    {
        "source_language": "en",
        "source_word": "towards",
        "bassa_word": "nyô",
        "category": "preposition",
        "notes": "Towards (direction)",
    },
    {
        "source_language": "en",
        "source_word": "behind",
        "bassa_word": "i mbuss",
        "category": "preposition",
        "notes": "Behind (spatial position)",
    },
]


def apply_corrections(db) -> int:
    fixed = 0
    for c in CORRECTIONS:
        entry = (
            db.query(DictionaryEntry)
            .filter(
                DictionaryEntry.source_language == c["source_language"],
                DictionaryEntry.source_word == c["source_word"],
                DictionaryEntry.bassa_word == c["old_bassa"],
            )
            .first()
        )
        if entry is None:
            print(f"  SKIP (not found or already fixed): [{c['source_language']}] {c['source_word']!r}")
            continue
        entry.bassa_word = c["new_bassa"]
        entry.notes = (entry.notes or "") + f" | Correction: {c['reason']}"
        fixed += 1
        print(f"  FIX: [{c['source_language']}] {c['source_word']!r}  {c['old_bassa']!r} -> {c['new_bassa']!r}")
    return fixed


def apply_additions(db) -> int:
    existing = {
        (e.source_language, e.source_word.lower(), e.bassa_word.lower())
        for e in db.query(DictionaryEntry).all()
    }
    added = 0
    for item in NEW_ENTRIES:
        key = (item["source_language"], item["source_word"].lower(), item["bassa_word"].lower())
        if key in existing:
            print(f"  SKIP (already exists): [{item['source_language']}] {item['source_word']!r} -> {item['bassa_word']!r}")
            continue
        entry = DictionaryEntry(
            source_language=item["source_language"],
            source_word=item["source_word"],
            bassa_word=item["bassa_word"],
            category=item.get("category"),
            notes=item.get("notes"),
            is_verified=True,
        )
        db.add(entry)
        existing.add(key)
        added += 1
        print(f"  ADD: [{item['source_language']}] {item['source_word']!r} -> {item['bassa_word']!r}")
    return added


def main():
    print("=== BassaAI Dictionary Enrichment ===")
    db = SessionLocal()
    try:
        print("\n--- Corrections ---")
        fixed = apply_corrections(db)

        print("\n--- Additions ---")
        added = apply_additions(db)

        db.commit()
        print(f"\nDone: {fixed} correction(s), {added} addition(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
