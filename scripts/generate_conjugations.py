"""Generate Bassa verb conjugations from existing dictionary entries.

Bassa present tense rule (confirmed from Je Parle Bassa 2.0):
  Conjugation = SUBJECT_PREFIX + n + VERB_STEM
  Prefixes: Me (je), U (tu), A (il/elle), Di (nous), Ni (vous), Ba (ils/elles)

Usage:
    python scripts/generate_conjugations.py [--dry-run] [--limit 500]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal
from backend.models.dictionary import DictionaryEntry

# Subject prefixes for present tense
PRESENT_PREFIXES = [
    ("je",   "Me"),
    ("tu",   "U"),
    ("il",   "A"),
    ("nous", "Di"),
    ("vous", "Ni"),
    ("ils",  "Ba"),
]

# French regular -er verb conjugation (covers ~90% of FR verbs)
def conjugate_fr_er(infinitive: str) -> dict[str, str]:
    stem = infinitive[:-2]

    # Spelling adjustments for -ger verbs (manger, voyager...)
    if stem.endswith("g"):
        nous_stem = stem + "e"
    # -cer verbs (placer, avancer...) - simplified, skip cedilla
    elif stem.endswith("c"):
        nous_stem = stem
    else:
        nous_stem = stem

    # Double consonant verbs: appeler→appelle, jeter→jette
    double_cons = ["appel", "jet", "rappel", "ficel", "epel"]
    if any(stem.endswith(d) for d in double_cons):
        stem2 = stem + stem[-1]  # double last consonant
    else:
        stem2 = stem

    return {
        "je":   f"je {stem2}e",
        "tu":   f"tu {stem2}es",
        "il":   f"il {stem2}e",
        "nous": f"nous {nous_stem}ons",
        "vous": f"vous {stem}ez",
        "ils":  f"ils {stem2}ent",
    }


# French -ir verb conjugation (finir, partir, sortir...)
def conjugate_fr_ir(infinitive: str) -> dict[str, str]:
    stem = infinitive[:-2]
    # finir-type: stem + iss for plural
    if len(stem) > 3:
        return {
            "je":   f"je {stem}is",
            "tu":   f"tu {stem}is",
            "il":   f"il {stem}it",
            "nous": f"nous {stem}issons",
            "vous": f"vous {stem}issez",
            "ils":  f"ils {stem}issent",
        }
    # partir-type: drop last consonant for singular
    else:
        return {
            "je":   f"je {stem[:-1]}s",
            "tu":   f"tu {stem[:-1]}s",
            "il":   f"il {stem[:-1]}t",
            "nous": f"nous {stem}ons",
            "vous": f"vous {stem}ez",
            "ils":  f"ils {stem}ent",
        }


# French -re verb conjugation (prendre, vendre...)
def conjugate_fr_re(infinitive: str) -> dict[str, str]:
    stem = infinitive[:-2]
    return {
        "je":   f"je {stem}s",
        "tu":   f"tu {stem}s",
        "il":   f"il {stem}",
        "nous": f"nous {stem}ons",
        "vous": f"vous {stem}ez",
        "ils":  f"ils {stem}ent",
    }


# Common irregular French verbs — handled manually to avoid bad forms
FR_IRREGULARS: dict[str, dict[str, str]] = {
    "aller":    {"je": "je vais",    "tu": "tu vas",    "il": "il va",      "nous": "nous allons",  "vous": "vous allez",  "ils": "ils vont"},
    "être":     {"je": "je suis",    "tu": "tu es",     "il": "il est",     "nous": "nous sommes",  "vous": "vous êtes",   "ils": "ils sont"},
    "avoir":    {"je": "j'ai",       "tu": "tu as",     "il": "il a",       "nous": "nous avons",   "vous": "vous avez",   "ils": "ils ont"},
    "faire":    {"je": "je fais",    "tu": "tu fais",   "il": "il fait",    "nous": "nous faisons", "vous": "vous faites", "ils": "ils font"},
    "dire":     {"je": "je dis",     "tu": "tu dis",    "il": "il dit",     "nous": "nous disons",  "vous": "vous dites",  "ils": "ils disent"},
    "pouvoir":  {"je": "je peux",    "tu": "tu peux",   "il": "il peut",    "nous": "nous pouvons", "vous": "vous pouvez", "ils": "ils peuvent"},
    "vouloir":  {"je": "je veux",    "tu": "tu veux",   "il": "il veut",    "nous": "nous voulons", "vous": "vous voulez", "ils": "ils veulent"},
    "savoir":   {"je": "je sais",    "tu": "tu sais",   "il": "il sait",    "nous": "nous savons",  "vous": "vous savez",  "ils": "ils savent"},
    "venir":    {"je": "je viens",   "tu": "tu viens",  "il": "il vient",   "nous": "nous venons",  "vous": "vous venez",  "ils": "ils viennent"},
    "voir":     {"je": "je vois",    "tu": "tu vois",   "il": "il voit",    "nous": "nous voyons",  "vous": "vous voyez",  "ils": "ils voient"},
    "prendre":  {"je": "je prends",  "tu": "tu prends", "il": "il prend",   "nous": "nous prenons", "vous": "vous prenez", "ils": "ils prennent"},
    "partir":   {"je": "je pars",    "tu": "tu pars",   "il": "il part",    "nous": "nous partons", "vous": "vous partez", "ils": "ils partent"},
    "sortir":   {"je": "je sors",    "tu": "tu sors",   "il": "il sort",    "nous": "nous sortons", "vous": "vous sortez", "ils": "ils sortent"},
    "dormir":   {"je": "je dors",    "tu": "tu dors",   "il": "il dort",    "nous": "nous dormons", "vous": "vous dormez", "ils": "ils dorment"},
    "mettre":   {"je": "je mets",    "tu": "tu mets",   "il": "il met",     "nous": "nous mettons", "vous": "vous mettez", "ils": "ils mettent"},
    "lire":     {"je": "je lis",     "tu": "tu lis",    "il": "il lit",     "nous": "nous lisons",  "vous": "vous lisez",  "ils": "ils lisent"},
    "écrire":   {"je": "j'écris",    "tu": "tu écris",  "il": "il écrit",   "nous": "nous écrivons","vous": "vous écrivez","ils": "ils écrivent"},
    "vivre":    {"je": "je vis",     "tu": "tu vis",    "il": "il vit",     "nous": "nous vivons",  "vous": "vous vivez",  "ils": "ils vivent"},
    "suivre":   {"je": "je suis",    "tu": "tu suis",   "il": "il suit",    "nous": "nous suivons", "vous": "vous suivez", "ils": "ils suivent"},
    "connaître":{"je": "je connais", "tu": "tu connais","il": "il connaît",  "nous": "nous connaissons","vous": "vous connaissez","ils": "ils connaissent"},
    "boire":    {"je": "je bois",    "tu": "tu bois",   "il": "il boit",    "nous": "nous buvons",  "vous": "vous buvez",  "ils": "ils boivent"},
    "recevoir": {"je": "je reçois",  "tu": "tu reçois", "il": "il reçoit",  "nous": "nous recevons","vous": "vous recevez","ils": "ils reçoivent"},
    "devoir":   {"je": "je dois",    "tu": "tu dois",   "il": "il doit",    "nous": "nous devons",  "vous": "vous devez",  "ils": "ils doivent"},
    "courir":   {"je": "je cours",   "tu": "tu cours",  "il": "il court",   "nous": "nous courons", "vous": "vous courez", "ils": "ils courent"},
    "mourir":   {"je": "je meurs",   "tu": "tu meurs",  "il": "il meurt",   "nous": "nous mourons", "vous": "vous mourez", "ils": "ils meurent"},
    "tenir":    {"je": "je tiens",   "tu": "tu tiens",  "il": "il tient",   "nous": "nous tenons",  "vous": "vous tenez",  "ils": "ils tiennent"},
    "ouvrir":   {"je": "j'ouvre",    "tu": "tu ouvres", "il": "il ouvre",   "nous": "nous ouvrons", "vous": "vous ouvrez", "ils": "ils ouvrent"},
    "offrir":   {"je": "j'offre",    "tu": "tu offres", "il": "il offre",   "nous": "nous offrons", "vous": "vous offrez", "ils": "ils offrent"},
}


def get_fr_conjugations(infinitive: str) -> dict[str, str] | None:
    if infinitive in FR_IRREGULARS:
        return FR_IRREGULARS[infinitive]
    if infinitive.endswith("er"):
        return conjugate_fr_er(infinitive)
    elif infinitive.endswith("ir"):
        return conjugate_fr_ir(infinitive)
    elif infinitive.endswith("re"):
        return conjugate_fr_re(infinitive)
    return None


def conjugate_bassa_present(stem: str) -> dict[str, str]:
    """Generate all 6 present tense forms: PREFIX + n + STEM."""
    return {fr_pron: f"{bas_pron} n{stem}" for fr_pron, bas_pron in PRESENT_PREFIXES}


def is_verb_infinitive(word: str) -> bool:
    """Heuristic: French infinitives end in -er, -ir, -re, -oir."""
    word = word.lower().strip()
    return bool(re.match(r'^[a-zàâéèêëîïôûùüçœæ\-]{3,}(er|ir|re|oir)$', word))


def generate(db, dry_run: bool = False, limit: int = 0) -> int:
    # Get all FR→Bassa verb entries
    query = db.query(DictionaryEntry).filter(
        DictionaryEntry.source_language == "fr"
    )
    all_entries = query.all()

    verbs = [e for e in all_entries if is_verb_infinitive(e.source_word)]
    print(f"  Verbes trouvés: {len(verbs)}")

    if limit:
        verbs = verbs[:limit]

    # Get existing words to avoid duplicates
    existing = {e.source_word.lower().strip() for e in all_entries}

    added = 0
    skipped_no_conj = 0

    for entry in verbs:
        infinitive = entry.source_word.lower().strip()
        bassa_stem = entry.bassa_word.strip()

        # Skip if stem looks invalid
        if len(bassa_stem) < 2 or not bassa_stem[0].isalpha():
            continue

        fr_conjs = get_fr_conjugations(infinitive)
        if not fr_conjs:
            skipped_no_conj += 1
            continue

        bas_conjs = conjugate_bassa_present(bassa_stem)

        for pron, fr_form in fr_conjs.items():
            fr_form_clean = fr_form.strip().lower()
            bas_form = bas_conjs[pron]

            if fr_form_clean in existing:
                continue

            if not dry_run:
                db.add(DictionaryEntry(
                    source_language = "fr",
                    source_word     = fr_form_clean,
                    bassa_word      = bas_form,
                    is_verified     = False,
                    notes           = f"Conjugaison présent de '{infinitive}' (auto-généré)",
                ))
            existing.add(fr_form_clean)
            added += 1

    if not dry_run:
        db.commit()

    return added


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Ne pas écrire en base")
    parser.add_argument("--limit", type=int, default=0, help="Limiter à N verbes (0=tous)")
    args = parser.parse_args()

    print("=== Générateur de conjugaisons Bassa ===")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'ECRITURE EN BASE'}")

    db = SessionLocal()
    try:
        # Preview first
        print("\n  Exemples de conjugaisons générées:")
        SAMPLES = [("aimer", "gwes"), ("parler", "pot"), ("aller", "ke"),
                   ("manger", "jé"), ("donner", "ti"), ("voir", None)]
        for fr, bas in SAMPLES:
            if not bas:
                continue
            fr_c = get_fr_conjugations(fr)
            bas_c = conjugate_bassa_present(bas)
            if fr_c:
                print(f"\n  {fr} (stem: {bas}):")
                for pron in ["je", "tu", "il", "nous", "vous", "ils"]:
                    print(f"    {fr_c[pron]:25s} -> {bas_c[pron]}")

        print(f"\n  Génération en cours...")
        added = generate(db, dry_run=args.dry_run, limit=args.limit)
        action = "générées (dry run)" if args.dry_run else "ajoutées en base"
        print(f"\n  {added} formes conjuguées {action}")

        if not args.dry_run:
            total = db.query(DictionaryEntry).count()
            print(f"  Total dictionnaire: {total} entrées")

    finally:
        db.close()

    print("\n=== Terminé! ===")


if __name__ == "__main__":
    main()
