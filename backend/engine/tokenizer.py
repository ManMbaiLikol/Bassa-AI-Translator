import re

# Common French contractions and their expansions
FR_CONTRACTIONS = {
    "l'": "le ",
    "d'": "de ",
    "j'": "je ",
    "n'": "ne ",
    "c'": "ce ",
    "s'": "se ",
    "m'": "me ",
    "t'": "te ",
    "qu'": "que ",
    "aujourd'hui": "aujourd'hui",  # Keep as single token
}

# French stop words that may be skipped in translation
FR_STOP_WORDS = {"le", "la", "les", "un", "une", "des", "du", "de", "à", "et", "est", "en", "que", "qui", "dans", "pour", "ce", "se"}

# English stop words
EN_STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "it", "this", "that"}

# Pre-compiled regex patterns (compiled once at module load, not on each call)
_RE_FR = re.compile(r"[a-zà-ÿ']+")
_RE_EN = re.compile(r"[a-z']+")

# Pre-sorted contractions (longest first) without the "aujourd'hui" special case
_FR_CONTRACTIONS_SORTED = sorted(
    [(k, v) for k, v in FR_CONTRACTIONS.items() if k != "aujourd'hui"],
    key=lambda x: len(x[0]),
    reverse=True,
)


def tokenize_french(text: str) -> list[str]:
    """Tokenize French text, expanding contractions."""
    text = text.lower().strip()

    # Expand contractions (pre-sorted by length, no re-sort on each call)
    for key, replacement in _FR_CONTRACTIONS_SORTED:
        text = text.replace(key, replacement)

    # Split into words using the pre-compiled pattern
    return _RE_FR.findall(text)


def tokenize_english(text: str) -> list[str]:
    """Tokenize English text."""
    text = text.lower().strip()
    return _RE_EN.findall(text)


def tokenize(text: str, language: str) -> list[str]:
    if language == "fr":
        return tokenize_french(text)
    return tokenize_english(text)
