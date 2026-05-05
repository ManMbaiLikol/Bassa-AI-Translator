"""Grammatical transformation rules for Bassa translation."""
import re


def apply_db_rules(word_results: list[dict], rules: list[dict]) -> list[dict]:
    """Apply admin-defined DB rules (GrammaticalRule) to the token list.

    Each rule's `pattern` is a regex matched against the source token.
    If it matches, `transformation` becomes the Bassa translation and the
    token is marked found=True — so hardcoded preposition-removal rules
    that only drop unfound tokens will preserve it.
    """
    result = list(word_results)
    for rule in rules:
        pattern = rule.get("pattern", "").strip()
        transformation = rule.get("transformation", "").strip()
        if not pattern:
            continue
        try:
            compiled = re.compile(f"^(?:{pattern})$", re.IGNORECASE | re.UNICODE)
        except re.error:
            continue
        for t in result:
            if compiled.match(t["source"]):
                t["translated"] = transformation
                t["found"] = True
    return result


def apply_french_rules(tokens: list[str], translated_tokens: list[dict]) -> list[dict]:
    """Apply French-to-Bassa grammatical transformations.

    Each token dict has: source, translated, found
    """
    result = list(translated_tokens)

    # Rule 1: Remove articles (le, la, les, un, une, des, du) - they don't exist in Bassa
    articles = {"le", "la", "les", "un", "une", "des", "du"}
    result = [t for t in result if t["source"] not in articles]

    # Rule 2: Remove prepositions that Bassa handles differently
    # "de" and "à" are removed; others like "avec", "dans", "pour" are kept if found in dict
    skip_prepositions = {"de", "à", "d"}
    result = [t for t in result if t["source"] not in skip_prepositions or t["found"]]

    # Rule 2b: Marqueur locatif — "au" / "aux" (à + le/les) → "i" en Bassa
    # En Bassa le déplacement vers un lieu se marque par le préfixe locatif "i",
    # jamais par l'article français contracté "au/aux".
    for t in result:
        if t["source"] in ("au", "aux") and not t["found"]:
            t["translated"] = "i"
            t["found"] = True

    # Rule 3: Handle negation "ne...pas" -> marqueur post-verbal "ɓé"
    # En Bassa la négation est post-verbale : "sujet + temps + verbe + ɓé + complément"
    # Source : LGMEF 2024 ex.9 "Kɛlâm a-ŋ-âŋ ɓé kaat" = "Kelam ne lit pas de livre"
    i = 0
    new_result = []
    while i < len(result):
        if result[i]["source"] == "ne":
            # Supprimer "ne" (la négation se marque par ɓé après le verbe)
            i += 1
            continue
        if result[i]["source"] == "pas":
            # Ajouter ɓé après le dernier mot traduit (= après le verbe)
            if new_result:
                new_result[-1]["translated"] += " ɓé"
            i += 1
            continue
        new_result.append(result[i])
        i += 1
    result = new_result

    return result


def apply_english_rules(tokens: list[str], translated_tokens: list[dict]) -> list[dict]:
    """Apply English-to-Bassa grammatical transformations."""
    result = list(translated_tokens)

    # Rule 1: Remove articles
    articles = {"the", "a", "an"}
    result = [t for t in result if t["source"] not in articles]

    # Rule 2: Remove auxiliary verbs that don't translate
    auxiliaries = {"is", "are", "was", "were", "do", "does", "did", "am"}
    result = [t for t in result if t["source"] not in auxiliaries]

    # Rule 3: Remove prepositions that don't map; keep those found in dict
    skip_preps = {"of", "to", "at"}
    result = [t for t in result if t["source"] not in skip_preps or t["found"]]

    return result


def apply_rules(tokens: list[str], translated_tokens: list[dict], language: str) -> list[dict]:
    if language == "fr":
        return apply_french_rules(tokens, translated_tokens)
    return apply_english_rules(tokens, translated_tokens)
