from backend.engine.tokenizer import tokenize_french, tokenize_english
from backend.engine.rule_transform import apply_french_rules, apply_english_rules


def test_tokenize_french():
    tokens = tokenize_french("Je mange du riz")
    assert "je" in tokens
    assert "mange" in tokens


def test_tokenize_french_contraction():
    tokens = tokenize_french("l'enfant de l'homme")
    assert "le" in tokens
    assert "enfant" in tokens


def test_tokenize_english():
    tokens = tokenize_english("I eat the food")
    assert tokens == ["i", "eat", "the", "food"]


def test_french_rules_remove_articles():
    tokens = ["je", "mange", "le", "riz"]
    word_results = [
        {"source": "je", "translated": "me", "found": True},
        {"source": "mange", "translated": "je", "found": True},
        {"source": "le", "translated": "le", "found": False},
        {"source": "riz", "translated": "riz", "found": False},
    ]
    result = apply_french_rules(tokens, word_results)
    sources = [r["source"] for r in result]
    assert "le" not in sources


def test_english_rules_remove_articles():
    tokens = ["i", "eat", "the", "food"]
    word_results = [
        {"source": "i", "translated": "me", "found": True},
        {"source": "eat", "translated": "je", "found": True},
        {"source": "the", "translated": "the", "found": False},
        {"source": "food", "translated": "bije", "found": True},
    ]
    result = apply_english_rules(tokens, word_results)
    sources = [r["source"] for r in result]
    assert "the" not in sources


def test_translate_endpoint(client):
    resp = client.post("/api/translate", json={
        "text": "bonjour",
        "source_language": "fr"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_language"] == "fr"
    assert "translated_text" in data
    assert "confidence" in data


def test_translate_empty(client):
    resp = client.post("/api/translate", json={
        "text": "   ",
        "source_language": "fr"
    })
    assert resp.status_code == 400


def test_translate_invalid_lang(client):
    resp = client.post("/api/translate", json={
        "text": "hello",
        "source_language": "de"
    })
    assert resp.status_code == 400
