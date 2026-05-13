"""Normalisation des marqueurs tonaux pour le Bassa.

Le Bassa utilise un système tonal écrit (â, ê, î, ô, û, á, é, í, ó, à, è, ǎ…).
Pour permettre la recherche tolérante aux accents, on stocke en plus la forme
sans marques diacritiques dans `DictionaryEntry.bassa_word_normalized`.
"""
from __future__ import annotations

import unicodedata

# Marques combinantes Unicode utilisées pour les tons en Bassa :
#   U+0300 grave  (à è ì ò ù)
#   U+0301 acute  (á é í ó ú)
#   U+0302 circumflex (â ê î ô û)
#   U+0303 tilde  (ã ñ õ)  — attention: ñ est une LETTRE en Bassa, pas un ton
#   U+0304 macron (ā ē ī)
#   U+0308 diaeresis (ä ë ï)
#   U+030C caron  (ǎ ě ǐ ǒ ǔ)
#
# On garde le tilde EXCLUSIVEMENT sur le n (ñ = ng vélaire) et on retire les autres.
TONAL_MARKS = {0x0300, 0x0301, 0x0302, 0x0304, 0x0308, 0x030C}


def strip_tones(text: str) -> str:
    """Supprime les marqueurs tonaux ; préserve ñ et autres lettres propres au Bassa.

    Exemples:
        strip_tones("nyó")   -> "nyo"
        strip_tones("sôñ")   -> "soñ"   (ñ conservé : c'est une lettre, pas un ton)
        strip_tones("Mè nlé") -> "Me nle"
    """
    if not text:
        return text
    nfd = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in nfd if ord(c) not in TONAL_MARKS)
    return unicodedata.normalize("NFC", stripped)


def has_tones(text: str) -> bool:
    """Indique si la chaîne contient au moins un marqueur tonal."""
    if not text:
        return False
    nfd = unicodedata.normalize("NFD", text)
    return any(ord(c) in TONAL_MARKS for c in nfd)


def normalize_for_search(text: str) -> str:
    """Forme canonique pour la recherche tolérante : sans tons, en minuscules,
    espaces internes réduits."""
    if not text:
        return text
    return " ".join(strip_tones(text).lower().split())
