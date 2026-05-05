"""Scrape the Glosbe FR→Bassa dictionary using Playwright (headless Chromium).

Usage:
    python scripts/scrape_glosbe.py [--limit 500] [--out backend/seed/glosbe_dictionary.json]

The script:
  1. Reads existing words from MySQL to avoid duplicates
  2. Iterates through a list of French words to look up
  3. For each word fetches https://fr.glosbe.com/fr/bas/<word>
  4. Waits for the client-side render to populate the translation
  5. Saves results to a JSON file (same format as expanded_dictionary.json)

After scraping, run seed_glosbe.py to import the JSON into MySQL.
"""

import argparse
import io
import json
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from backend.database import SessionLocal
from backend.models.dictionary import DictionaryEntry

# ---------------------------------------------------------------------------
# French word list to look up — start with the 1000 most common French words
# that are most useful for translation (nouns, verbs, adjectives, prepositions)
# ---------------------------------------------------------------------------
FRENCH_WORDS = [
    # Pronouns
    "je", "tu", "il", "elle", "nous", "vous", "ils", "elles",
    "moi", "toi", "lui", "soi", "eux",
    "me", "te", "se", "le", "la", "les", "lui", "leur", "y", "en",
    "qui", "que", "quoi", "dont", "où",
    # Common verbs (infinitive)
    "être", "avoir", "aller", "venir", "faire", "dire", "voir",
    "savoir", "pouvoir", "vouloir", "devoir", "falloir",
    "prendre", "donner", "parler", "aimer", "manger", "boire",
    "dormir", "travailler", "lire", "écrire", "entendre", "comprendre",
    "penser", "croire", "regarder", "marcher", "courir", "chanter",
    "danser", "rire", "pleurer", "attendre", "partir", "arriver",
    "rester", "revenir", "ouvrir", "fermer", "tomber", "lever",
    "asseoir", "chercher", "trouver", "perdre", "gagner", "appeler",
    "répondre", "demander", "aider", "jouer", "apprendre", "enseigner",
    "acheter", "vendre", "payer", "porter", "mettre", "tenir",
    "montrer", "laisser", "suivre", "connaître", "rencontrer",
    # Nouns — body
    "tête", "main", "pied", "bras", "jambe", "dos", "ventre",
    "bouche", "yeux", "oreille", "nez", "dent", "coeur", "sang",
    # Nouns — family
    "père", "mère", "fils", "fille", "frère", "soeur", "enfant",
    "grand-père", "grand-mère", "oncle", "tante", "cousin", "cousine",
    # Nouns — nature / environment
    "soleil", "lune", "étoile", "ciel", "pluie", "vent", "feu",
    "eau", "terre", "mer", "rivière", "forêt", "arbre", "fleur",
    "animal", "oiseau", "poisson", "serpent", "lion", "chien", "chat",
    # Nouns — time
    "jour", "nuit", "matin", "soir", "heure", "minute", "semaine",
    "mois", "année", "an", "aujourd'hui", "demain", "hier", "maintenant",
    # Nouns — place / objects
    "maison", "village", "ville", "route", "chemin", "porte", "fenêtre",
    "table", "chaise", "lit", "cuisine", "salle", "école", "église",
    "marché", "champ", "pierre", "bois",
    # Nouns — food
    "pain", "riz", "viande", "poule", "poisson", "légume", "fruit",
    "sel", "sucre", "huile", "lait",
    # Adjectives
    "grand", "petit", "bon", "mauvais", "beau", "vieux", "jeune",
    "fort", "faible", "rapide", "lent", "chaud", "froid", "long",
    "court", "plein", "vide", "lourd", "léger", "riche", "pauvre",
    "blanc", "noir", "rouge", "bleu", "vert", "jaune",
    # Prepositions / adverbs
    "avec", "sans", "dans", "sur", "sous", "devant", "derrière",
    "avant", "après", "entre", "vers", "par", "pour", "contre",
    "chez", "depuis", "jusqu", "pendant",
    "ici", "là", "dessus", "dessous", "dedans", "dehors",
    "toujours", "jamais", "souvent", "parfois", "encore", "déjà",
    "beaucoup", "peu", "très", "trop", "assez", "aussi", "seulement",
    "oui", "non", "peut-être", "voilà", "voici",
    # Numbers
    "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit",
    "neuf", "dix", "vingt", "cent", "mille",
    # Common phrases
    "bonjour", "bonsoir", "bonne nuit", "merci", "pardon", "comment",
    "pourquoi", "quand", "combien",
]


def get_existing_words(db) -> set:
    """Return set of (language, word) tuples already in the database."""
    return {
        (e.source_language, e.source_word.lower())
        for e in db.query(DictionaryEntry).filter(DictionaryEntry.source_language == "fr").all()
    }


def scrape_word(page, word: str) -> dict | None:
    """Fetch translation for a single French word from Glosbe. Returns None if not found."""
    import re

    url = f"https://fr.glosbe.com/fr/bas/{word}"
    try:
        page.goto(url, timeout=20000, wait_until="networkidle")
    except PWTimeout:
        return None
    except Exception:
        return None

    try:
        body_text = page.locator("body").inner_text(timeout=5000)
    except Exception:
        return None

    # Pattern: "X est la traduction de 'word' en bassa"
    escaped = re.escape(word)
    m = re.search(
        rf'(.+?)\s+est la traduction de\s+["\u201c\u00ab]?{escaped}["\u201d\u00bb]?\s+en bassa',
        body_text,
        re.IGNORECASE,
    )
    # Reject phrases that indicate no translation (French error messages)
    _NO_TRANS_MARKERS = ("actuellement", "n'avons pas", "pas de traduction", "ajouter une")

    if m:
        bassa_word = m.group(1).strip()
        low = bassa_word.lower()
        if (
            len(bassa_word) > 40
            or bassa_word.lower() == word.lower()
            or any(marker in low for marker in _NO_TRANS_MARKERS)
        ):
            return None
        return {
            "source_language": "fr",
            "source_word": word.lower(),
            "bassa_word": bassa_word,
            "category": "",
            "notes": "Glosbe fr/bas",
        }

    # Fallback: look for "DICTIONNAIRE FRANÇAIS - BASSA\n<bassa_word>\n<french_word>"
    dict_m = re.search(
        r'DICTIONNAIRE FRAN[Ç|C]AIS - BASSA\s+(.+?)\s+' + re.escape(word.capitalize()),
        body_text,
        re.IGNORECASE | re.DOTALL,
    )
    if dict_m:
        bassa_word = dict_m.group(1).strip().splitlines()[0].strip()
        low = bassa_word.lower()
        if (
            bassa_word
            and len(bassa_word) <= 40
            and bassa_word.lower() != word.lower()
            and not any(marker in low for marker in _NO_TRANS_MARKERS)
        ):
            return {
                "source_language": "fr",
                "source_word": word.lower(),
                "bassa_word": bassa_word,
                "category": "",
                "notes": "Glosbe fr/bas (fallback)",
            }

    return None


def main():
    parser = argparse.ArgumentParser(description="Scrape Glosbe FR→Bassa")
    parser.add_argument("--limit", type=int, default=0, help="Max words to scrape (0=all)")
    parser.add_argument("--out", default="backend/seed/glosbe_dictionary.json")
    args = parser.parse_args()

    out_path = Path(args.out)

    db = SessionLocal()
    existing = get_existing_words(db)
    db.close()

    words = [w for w in FRENCH_WORDS if ("fr", w.lower()) not in existing]
    if args.limit:
        words = words[: args.limit]

    print(f"Words to scrape: {len(words)} (skipping {len(FRENCH_WORDS) - len(words)} already in DB)")

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # Block images/fonts to speed up loading
        page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf}", lambda r: r.abort())

        for i, word in enumerate(words):
            entry = scrape_word(page, word)
            if entry:
                results.append(entry)
                print(f"  [{i+1}/{len(words)}] {word!r} -> {entry['bassa_word']!r}")
            else:
                print(f"  [{i+1}/{len(words)}] {word!r} -> (not found)")
            # Polite delay
            time.sleep(0.5)

        browser.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(results)} entries to {out_path}")


if __name__ == "__main__":
    main()
