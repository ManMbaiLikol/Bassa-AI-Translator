"""Tests pour les helpers de normalisation tonale Bassa."""
import pytest

from backend.services.tonal import has_tones, normalize_for_search, strip_tones


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("nyó", "nyo"),
        ("sôñ", "soñ"),  # ñ est une LETTRE en Bassa, pas un ton
        ("Mè nlé", "Me nle"),
        ("nsômbi", "nsombi"),
        ("nyo", "nyo"),  # déjà sans tons
        ("lélé", "lele"),
        ("ǎbě", "abe"),
        ("", ""),
        ("aujourd'hui", "aujourd'hui"),  # apostrophe préservée
    ],
)
def test_strip_tones(input_text, expected):
    assert strip_tones(input_text) == expected


def test_has_tones():
    assert has_tones("nyó") is True
    assert has_tones("sôñ") is True
    assert has_tones("nyo") is False
    assert has_tones("soñ") is False  # ñ seul n'est pas un ton
    assert has_tones("") is False


def test_normalize_for_search_collapses_whitespace_and_case():
    assert normalize_for_search("  Mè  NLé  ") == "me nle"
    assert normalize_for_search("Sôñ") == "soñ"
