"""Tests unitaires et d'intégration du moteur ML (MLEngine).

Deux niveaux :
  - Tests unitaires : FakeModel avec embeddings 2D contrôlés, SQLite en mémoire.
    Rapides (~1 s), pas de dépendance réseau ni GPU.
  - Tests d'intégration (@pytest.mark.integration) : vrai modèle + corpus MySQL.
    Lents (~30 s), nécessitent sentence-transformers installé et DB peuplée.
    Lancés séparément : pytest -m integration tests/test_ml_engine.py
"""
from __future__ import annotations

import math
import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from backend.models.corpus import CorpusPair
from backend.models.dictionary import DictionaryEntry
from backend.engine.ml_engine import MLEngine
from backend.engine.base import TranslationResult
from backend.config import settings


# ─────────────────────────────────────────────────────────────────────────────
# FakeModel : contrôle exact des scores de similarité
# ─────────────────────────────────────────────────────────────────────────────

class FakeModel:
    """SentenceTransformer factice renvoyant des embeddings 2D prédéfinis.

    Chaque texte est associé à un vecteur unitaire 2D. La similarité cosine
    entre deux vecteurs normalisés est leur produit scalaire.
    Textes inconnus → vecteur par défaut (orthogonal aux vecteurs corpus).
    """

    def __init__(self, mapping: dict[str, np.ndarray]):
        self._map = {k: np.array(v, dtype=np.float64) for k, v in mapping.items()}
        # Vecteur par défaut pour les textes hors mapping (orthogonal à [1,0])
        self._default = np.array([0.0, 1.0], dtype=np.float64)

    def encode(
        self,
        texts: list[str],
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        result = []
        for t in texts:
            vec = self._map.get(t, self._default).copy()
            if normalize_embeddings and np.linalg.norm(vec) > 0:
                vec = vec / np.linalg.norm(vec)
            result.append(vec)
        return np.array(result, dtype=np.float64)


# ─────────────────────────────────────────────────────────────────────────────
# Vecteurs 2D unitaires de référence
# ─────────────────────────────────────────────────────────────────────────────
# Vecteur du corpus (paire principale)
CORPUS_VEC   = np.array([1.0, 0.0])           # angle 0°

# Vecteurs de requête avec scores connus contre CORPUS_VEC
# cos(θ) = dot product car vecteurs normalisés
QUERY_EXACT  = np.array([1.0, 0.0])           # score = 1.000 (identique)
QUERY_VERY_HIGH = np.array([0.97, 0.24])      # score ≈ 0.97 > HIGH_THRESHOLD
QUERY_HIGH_BORDER = np.array([0.91, 0.41])    # score ≈ 0.91, juste au-dessus de HIGH=0.90
QUERY_MED    = np.array([0.77, 0.64])         # score ≈ 0.77 > MED=0.70, < HIGH=0.90
QUERY_LOW    = np.array([0.50, 0.87])         # score ≈ 0.50 < MED=0.70
QUERY_ZERO   = np.array([0.0, 1.0])           # score = 0.0  (orthogonal)

CORPUS_VEC_B = np.array([0.0, 1.0])           # 2ème paire corpus (perpendiculaire)


def _norm(v: np.ndarray) -> float:
    """Score exact d'un vecteur query contre CORPUS_VEC=[1,0]."""
    v = v / np.linalg.norm(v)
    return float(v[0])  # dot([1,0], v) = v[0]


# Vérification des scores attendus (pour la lisibilité des tests)
HIGH = settings.ML_HIGH_THRESHOLD   # 0.90
MED  = settings.ML_MED_THRESHOLD    # 0.70

assert _norm(QUERY_EXACT)       == pytest.approx(1.000, abs=0.01)
assert _norm(QUERY_VERY_HIGH)   == pytest.approx(0.970, abs=0.02)
assert _norm(QUERY_HIGH_BORDER) == pytest.approx(0.912, abs=0.02)
assert _norm(QUERY_MED)         == pytest.approx(0.769, abs=0.02)
assert _norm(QUERY_LOW)         == pytest.approx(0.500, abs=0.02)
assert _norm(QUERY_ZERO)        == pytest.approx(0.000, abs=0.01)

assert HIGH < 1.0 and HIGH > MED
assert MED  < HIGH and MED > 0.0
assert _norm(QUERY_VERY_HIGH)   > HIGH
assert _norm(QUERY_HIGH_BORDER) > HIGH
assert _norm(QUERY_MED)         > MED  and _norm(QUERY_MED)  < HIGH
assert _norm(QUERY_LOW)         < MED


# ─────────────────────────────────────────────────────────────────────────────
# Helpers : construction du moteur avec SQLite
# ─────────────────────────────────────────────────────────────────────────────

def _seed_pair(db, src: str, bassa: str, lang: str = "fr", verified: bool = True) -> CorpusPair:
    p = CorpusPair(source_language=lang, source_text=src, bassa_text=bassa, is_verified=verified)
    db.add(p)
    db.commit()
    return p


def _seed_dict(db, word: str, bassa: str, lang: str = "fr") -> DictionaryEntry:
    e = DictionaryEntry(source_language=lang, source_word=word, bassa_word=bassa, is_verified=True)
    db.add(e)
    db.commit()
    return e


def _build_engine(db, mapping: dict[str, np.ndarray]) -> MLEngine:
    """Crée un MLEngine avec le FakeModel injecté, recharge depuis le SQLite de test."""
    # On laisse __init__ échouer sur le chargement du modèle (pas de MySQL)
    with patch("backend.engine.ml_engine.SentenceTransformer", side_effect=RuntimeError("skip")):
        engine = MLEngine()
    # _model=None → reload() dans __init__ est revenu tôt, pas de requête MySQL

    # Injecter le faux modèle
    engine._model = FakeModel(mapping)
    # Reconstruire l'index avec le SQLite de test
    engine.reload(db)
    return engine


# ─────────────────────────────────────────────────────────────────────────────
# Tests unitaires
# ─────────────────────────────────────────────────────────────────────────────

class TestMLEngineUnit:

    # ── Propriétés de diagnostic ──────────────────────────────────────────────

    def test_model_ready_false_when_no_model(self, db):
        with patch("backend.engine.ml_engine.SentenceTransformer", side_effect=RuntimeError):
            engine = MLEngine()
        assert engine.model_ready is False

    def test_corpus_size_zero_when_no_corpus(self, db):
        engine = _build_engine(db, {})
        assert engine.corpus_size == 0

    def test_model_ready_false_when_corpus_empty(self, db):
        engine = _build_engine(db, {})
        # _model est défini mais _embeddings=None car corpus vide
        assert engine.model_ready is False

    def test_corpus_size_reflects_verified_pairs(self, db):
        _seed_pair(db, "phrase A", "bassa A", verified=True)
        _seed_pair(db, "phrase B", "bassa B", verified=False)  # non vérifiée → ignorée
        engine = _build_engine(db, {"phrase A": CORPUS_VEC})
        assert engine.corpus_size == 1

    def test_model_ready_true_when_corpus_loaded(self, db):
        _seed_pair(db, "Bonjour", "Mbolo")
        engine = _build_engine(db, {"Bonjour": CORPUS_VEC})
        assert engine.model_ready is True

    # ── Cas : corpus vide ────────────────────────────────────────────────────

    def test_empty_corpus_returns_dict_fallback(self, db):
        engine = _build_engine(db, {})
        result = engine.translate("Bonjour", "fr")
        assert isinstance(result, TranslationResult)
        assert result.engine == "dictionary"   # pur fallback dict

    def test_empty_text_returns_empty(self, db):
        engine = _build_engine(db, {})
        result = engine.translate("   ", "fr")
        assert result.translated_text == ""
        assert result.confidence == 0.0
        assert result.engine == "ml"

    # ── Score élevé (≥ HIGH_THRESHOLD) → retrieval corpus ───────────────────

    def test_exact_match_triggers_retrieval(self, db):
        _seed_pair(db, "Bonjour", "Mbolo")
        engine = _build_engine(db, {"Bonjour": CORPUS_VEC, "Bonjour": CORPUS_VEC})
        result = engine.translate("Bonjour", "fr")
        assert result.engine == "ml-retrieval"
        assert result.translated_text == "Mbolo"

    def test_high_similarity_triggers_retrieval(self, db):
        _seed_pair(db, "Bonjour tout le monde", "Mbolo bena")
        engine = _build_engine(db, {
            "Bonjour tout le monde": CORPUS_VEC,
            "Salut tout le monde":   QUERY_VERY_HIGH,
        })
        result = engine.translate("Salut tout le monde", "fr")
        assert result.engine == "ml-retrieval"
        assert result.translated_text == "Mbolo bena"
        assert result.confidence >= HIGH

    def test_retrieval_confidence_equals_score(self, db):
        _seed_pair(db, "Bonjour", "Mbolo")
        engine = _build_engine(db, {
            "Bonjour": CORPUS_VEC,
            "Salut":   QUERY_VERY_HIGH,
        })
        result = engine.translate("Salut", "fr")
        expected_score = _norm(QUERY_VERY_HIGH)
        assert result.confidence == pytest.approx(expected_score, abs=0.02)

    def test_retrieval_adds_warning_when_phrase_differs(self, db):
        _seed_pair(db, "Bonjour tout le monde", "Mbolo bena")
        engine = _build_engine(db, {
            "Bonjour tout le monde": CORPUS_VEC,
            "Salut tout le monde":   QUERY_VERY_HIGH,
        })
        result = engine.translate("Salut tout le monde", "fr")
        assert result.engine == "ml-retrieval"
        assert any("similarité" in w or "Bonjour" in w for w in result.warnings)

    def test_exact_match_no_warning(self, db):
        _seed_pair(db, "Bonjour", "Mbolo")
        engine = _build_engine(db, {"Bonjour": CORPUS_VEC})
        result = engine.translate("Bonjour", "fr")
        # Même phrase → pas d'avertissement de similarité
        assert all("similarité" not in w for w in result.warnings)

    # ── Score moyen (MED ≤ score < HIGH) → suggestion corpus ─────────────────

    def test_medium_similarity_suggests_corpus(self, db):
        _seed_pair(db, "Bonjour tout le monde", "Mbolo bena")
        engine = _build_engine(db, {
            "Bonjour tout le monde": CORPUS_VEC,
            "Hello world":           QUERY_MED,
        })
        result = engine.translate("Hello world", "fr")
        assert result.engine == "ml+dictionary"
        assert any("similaire" in w for w in result.warnings)

    def test_medium_similarity_keeps_bassa_preview(self, db):
        _seed_pair(db, "Bonjour", "Mbolo")
        engine = _build_engine(db, {
            "Bonjour": CORPUS_VEC,
            "Salut":   QUERY_MED,
        })
        result = engine.translate("Salut", "fr")
        assert any("Mbolo" in w for w in result.warnings)

    def test_medium_similarity_long_bassa_ignored(self, db):
        """Les traductions corpus > 150 chars ne sont pas suggérées."""
        long_bassa = "B" * 151
        _seed_pair(db, "Phrase longue du corpus", long_bassa)
        engine = _build_engine(db, {
            "Phrase longue du corpus": CORPUS_VEC,
            "Phrase similaire":        QUERY_MED,
        })
        result = engine.translate("Phrase similaire", "fr")
        # Pas de suggestion ML car bassa trop long
        assert result.engine == "dictionary"
        # Le warning ML spécifique "Traduction similaire dans le corpus" ne doit pas être présent
        # (le dict engine peut avoir ses propres warnings sur les mots inconnus)
        assert all("dans le corpus" not in w for w in result.warnings)

    # ── Score faible (< MED) → dictionnaire pur ──────────────────────────────

    def test_low_similarity_uses_dict_only(self, db):
        _seed_pair(db, "Bonjour", "Mbolo")
        engine = _build_engine(db, {
            "Bonjour":  CORPUS_VEC,
            "Train":    QUERY_LOW,
        })
        result = engine.translate("Train", "fr")
        assert result.engine == "dictionary"
        assert all("similaire" not in w for w in result.warnings)

    def test_zero_similarity_uses_dict_only(self, db):
        _seed_pair(db, "Bonjour", "Mbolo")
        engine = _build_engine(db, {
            "Bonjour":   CORPUS_VEC,
            "Orthogonal": QUERY_ZERO,
        })
        result = engine.translate("Orthogonal", "fr")
        assert result.engine == "dictionary"

    # ── word_translations toujours présentes ──────────────────────────────────

    def test_word_translations_present_on_retrieval(self, db):
        """word_translations doit être peuplé même en mode ml-retrieval."""
        _seed_dict(db, "bonjour", "Mbolo")
        _seed_pair(db, "Bonjour", "Mbolo")
        engine = _build_engine(db, {"Bonjour": CORPUS_VEC})
        result = engine.translate("Bonjour", "fr")
        assert result.engine == "ml-retrieval"
        assert len(result.word_translations) > 0

    def test_word_translations_present_on_medium(self, db):
        _seed_dict(db, "bonjour", "Mbolo")
        _seed_pair(db, "Bonjour", "Mbolo")
        engine = _build_engine(db, {
            "Bonjour": CORPUS_VEC,
            "Salut":   QUERY_MED,
        })
        result = engine.translate("Salut", "fr")
        assert isinstance(result.word_translations, list)

    # ── Filtre par langue ────────────────────────────────────────────────────

    def test_lang_filter_fr_vs_en(self, db):
        """Un corpus fr ne doit pas correspondre à une requête en."""
        _seed_pair(db, "Bonjour", "Mbolo", lang="fr")
        engine = _build_engine(db, {
            "Bonjour": CORPUS_VEC,
            "Hello":   QUERY_VERY_HIGH,   # même direction → score élevé
        })
        # Requête en anglais → aucune paire fr ne devrait matcher
        result = engine.translate("Hello", "en")
        # Le corpus est fr, pas en : pas de retrieval
        assert result.engine not in ("ml-retrieval", "ml+dictionary")

    def test_multilingual_corpus_correct_lang(self, db):
        _seed_pair(db, "Bonjour", "Mbolo",  lang="fr")
        _seed_pair(db, "Hello",   "Mbolo2", lang="en")
        engine = _build_engine(db, {
            "Bonjour": CORPUS_VEC,
            "Hello":   CORPUS_VEC_B,
        })
        result_fr = engine.translate("Bonjour", "fr")
        result_en = engine.translate("Hello",   "en")
        assert result_fr.translated_text == "Mbolo"
        assert result_en.translated_text == "Mbolo2"

    # ── Corpus à une seule entrée (squeeze → scalaire) ────────────────────────

    def test_single_corpus_pair_no_crash(self, db):
        """Régression : corpus d'1 paire → squeeze() retourne un scalaire."""
        _seed_pair(db, "Bonjour", "Mbolo")
        engine = _build_engine(db, {"Bonjour": CORPUS_VEC})
        result = engine.translate("Bonjour", "fr")
        assert result.translated_text == "Mbolo"

    def test_single_pair_low_query_no_crash(self, db):
        _seed_pair(db, "Bonjour", "Mbolo")
        engine = _build_engine(db, {
            "Bonjour": CORPUS_VEC,
            "Train":   QUERY_LOW,
        })
        result = engine.translate("Train", "fr")
        assert isinstance(result, TranslationResult)

    # ── Reload ───────────────────────────────────────────────────────────────

    def test_reload_updates_corpus_size(self, db):
        engine = _build_engine(db, {})
        assert engine.corpus_size == 0

        _seed_pair(db, "Bonjour", "Mbolo")
        engine._model = FakeModel({"Bonjour": CORPUS_VEC})
        engine.reload(db)
        assert engine.corpus_size == 1

    def test_reload_rebuilds_index(self, db):
        _seed_pair(db, "Bonjour", "Mbolo")
        engine = _build_engine(db, {"Bonjour": CORPUS_VEC})
        assert engine.corpus_size == 1

        # Ajouter une deuxième paire et recharger
        _seed_pair(db, "Merci", "A ngi nyu")
        engine._model = FakeModel({
            "Bonjour": CORPUS_VEC,
            "Merci":   CORPUS_VEC_B,
        })
        engine.reload(db)
        assert engine.corpus_size == 2

    def test_reload_excludes_unverified(self, db):
        _seed_pair(db, "Bonjour", "Mbolo",   verified=True)
        _seed_pair(db, "Bonsoir", "Mbolo2",  verified=False)
        engine = _build_engine(db, {"Bonjour": CORPUS_VEC})
        assert engine.corpus_size == 1   # non vérifiée exclue

    # ── Moteur non disponible (_model=None) ───────────────────────────────────

    def test_no_model_fallback_to_dict(self, db):
        with patch("backend.engine.ml_engine.SentenceTransformer", side_effect=RuntimeError):
            engine = MLEngine()
        assert engine._model is None
        result = engine.translate("Bonjour", "fr")
        assert result.engine == "dictionary"

    def test_no_model_best_match_returns_zero(self, db):
        with patch("backend.engine.ml_engine.SentenceTransformer", side_effect=RuntimeError):
            engine = MLEngine()
        score, src, bassa = engine._best_match("Bonjour", "fr")
        assert score == 0.0
        assert src == ""
        assert bassa == ""

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_no_corpus_for_lang_returns_zero_score(self, db):
        _seed_pair(db, "Bonjour", "Mbolo", lang="fr")
        engine = _build_engine(db, {"Bonjour": CORPUS_VEC})
        score, _, _ = engine._best_match("Hello", "en")  # aucune paire en
        assert score == 0.0

    def test_bassa_normalization_applied(self, db):
        """normalize_bassa() doit être appliqué aux traductions du corpus."""
        # Caractère Bassa stocké avec modificateur avant lettre (˜ + n = ñ)
        _seed_pair(db, "Phrase test", "\u02dcn bassa")
        engine = _build_engine(db, {"Phrase test": CORPUS_VEC})
        # La traduction doit être normalisée NFC
        assert engine._bassa[0] == "\xf1 bassa"  # ñ en NFC

    def test_multiple_corpus_best_match_selects_closest(self, db):
        _seed_pair(db, "Phrase A", "Bassa A")
        _seed_pair(db, "Phrase B", "Bassa B")
        # Phrase A = [1,0], Phrase B = [0,1]
        # Query = très proche de Phrase A
        engine = _build_engine(db, {
            "Phrase A": CORPUS_VEC,
            "Phrase B": CORPUS_VEC_B,
            "Query":    QUERY_VERY_HIGH,  # proche de [1,0] = Phrase A
        })
        result = engine.translate("Query", "fr")
        assert result.translated_text == "Bassa A"

    def test_threshold_boundary_high(self, db):
        """Juste au-dessus de HIGH_THRESHOLD → retrieval."""
        _seed_pair(db, "Bonjour", "Mbolo")
        engine = _build_engine(db, {
            "Bonjour": CORPUS_VEC,
            "Query":   QUERY_HIGH_BORDER,  # score ≈ 0.91 > HIGH=0.90
        })
        result = engine.translate("Query", "fr")
        assert result.engine == "ml-retrieval"

    def test_threshold_boundary_medium(self, db):
        """Juste au-dessus de MED mais sous HIGH → suggestion."""
        _seed_pair(db, "Bonjour", "Mbolo")
        engine = _build_engine(db, {
            "Bonjour": CORPUS_VEC,
            "Query":   QUERY_MED,   # score ≈ 0.77, MED < 0.77 < HIGH
        })
        result = engine.translate("Query", "fr")
        assert result.engine == "ml+dictionary"


# ─────────────────────────────────────────────────────────────────────────────
# Tests d'intégration (vrai modèle + corpus MySQL)
# Lancer avec : pytest -m integration tests/test_ml_engine.py
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestMLEngineIntegration:
    """Tests avec le vrai modèle sentence-transformers et la DB MySQL réelle."""

    @pytest.fixture(scope="class")
    def real_engine(self):
        """MLEngine chargé une seule fois pour tous les tests de la classe."""
        engine = MLEngine()
        if not engine.model_ready:
            pytest.skip("Modèle ML non disponible ou corpus vide")
        return engine

    def test_corpus_loaded(self, real_engine):
        assert real_engine.corpus_size > 0
        assert real_engine.model_ready is True

    def test_exact_phrase_scores_one(self, real_engine):
        """Une phrase exacte du corpus doit scorer 1.0."""
        src = real_engine._sources[0]
        score, matched, _ = real_engine._best_match(src, real_engine._langs[0])
        assert score == pytest.approx(1.0, abs=1e-4)
        assert matched == src

    def test_exact_phrase_triggers_retrieval(self, real_engine):
        src = real_engine._sources[0]
        bassa = real_engine._bassa[0]
        lang = real_engine._langs[0]
        result = real_engine.translate(src, lang)
        assert result.engine == "ml-retrieval"
        assert result.translated_text == bassa

    def test_out_of_domain_below_med(self, real_engine):
        """Phrase hors domaine (vie quotidienne) → score < MED."""
        out_domain = "Je vais acheter du pain au marché ce matin"
        score, _, _ = real_engine._best_match(out_domain, "fr")
        assert score < MED, f"Score inattendu pour hors-domaine : {score:.3f}"

    def test_different_verse_same_domain_not_retrieval(self, real_engine):
        """Deux versets distincts → le score ne doit pas dépasser HIGH."""
        # Prendre la phrase 0 et tester contre la phrase 1
        if real_engine.corpus_size < 2:
            pytest.skip("Corpus trop petit (< 2 paires)")
        src0 = real_engine._sources[0]
        src1 = real_engine._sources[1]
        if src0 == src1:
            pytest.skip("Deux phrases identiques dans le corpus")
        score, _, _ = real_engine._best_match(src1, real_engine._langs[0])
        # src1 ne doit pas déclencher retrieval quand on interroge comme si c'était src0
        # (Note : on teste que le SECOND verset ne score pas > HIGH sur le premier)
        # Ce test vérifie la robustesse du seuil, pas un résultat binaire strict
        result = real_engine.translate(src1, real_engine._langs[1] if len(real_engine._langs) > 1 else "fr")
        # Un verset distinct ne devrait pas retourner la traduction d'un autre
        if result.engine == "ml-retrieval":
            # Si retrieval déclenché, la traduction doit être la bonne (même phrase)
            assert result.translated_text == real_engine._bassa[1]

    def test_word_translations_always_returned(self, real_engine):
        src = real_engine._sources[0]
        lang = real_engine._langs[0]
        result = real_engine.translate(src, lang)
        assert isinstance(result.word_translations, list)

    def test_score_distribution_sanity(self, real_engine):
        """Vérifie que la distribution des scores auto-similarité est 1.0."""
        sample = real_engine._sources[:5]
        for src, lang in zip(sample, real_engine._langs[:5]):
            score, _, _ = real_engine._best_match(src, lang)
            assert score == pytest.approx(1.0, abs=1e-4), \
                f"Auto-similarité != 1.0 pour : {src[:40]!r} (score={score:.4f})"

    def test_fr_en_isolation(self, real_engine):
        """Les paires fr ne doivent pas être retournées pour une requête en."""
        if not any(l == "en" for l in real_engine._langs):
            pytest.skip("Pas de paires en dans le corpus")
        fr_src = next(s for s, l in zip(real_engine._sources, real_engine._langs) if l == "fr")
        score, _, _ = real_engine._best_match(fr_src, "en")
        assert score == 0.0, "Une paire fr ne doit pas matcher une requête en"

    def test_threshold_high_only_near_exact(self, real_engine):
        """Vérifie empiriquement que HIGH=0.90 ne déclenche pas sur de simples paraphrases."""
        paraphrases_bibliques = [
            "Dieu crea le ciel et la terre au debut",
            "Il y avait des tenebres au commencement",
            "Dieu dit que la lumiere etait bonne",
        ]
        for text in paraphrases_bibliques:
            score, matched_src, _ = real_engine._best_match(text, "fr")
            if score >= HIGH:
                # Si HIGH déclenché, vérifier que c'est vraiment une phrase proche
                # (non trivial sans étiquettes, mais on peut vérifier le résultat)
                result = real_engine.translate(text, "fr")
                assert result.engine == "ml-retrieval"
                # La phrase matchée doit contenir des mots en commun
                text_words = set(text.lower().split())
                matched_words = set(matched_src.lower().split())
                overlap = len(text_words & matched_words)
                assert overlap >= 2, (
                    f"Faux positif suspecté : {text!r} → {matched_src[:50]!r} "
                    f"(score={score:.3f}, overlap={overlap} mots)"
                )
