"""Phase 2: Moteur ML hybride — recherche sémantique dans le corpus + fallback dictionnaire.

Fonctionnement :
  1. Au démarrage (ou reload), encode toutes les phrases source du corpus
     en vecteurs d'embeddings multilingues (sentence-transformers).
  2. Pour chaque traduction, calcule la similarité cosinus entre l'entrée
     et toutes les phrases du corpus.
  3. Si la similarité dépasse le seuil haut → retourne la traduction du corpus.
  4. Si la similarité est modérée → enrichit le résultat du dictionnaire
     avec la suggestion du corpus.
  5. Sinon → délègue entièrement au DictionaryEngine.

Apprentissage automatique : chaque contribution approuvée fait grossir le corpus,
ce qui élargit l'index et améliore les futures traductions.
"""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.engine.base import TranslationEngine, TranslationResult
from backend.engine.dictionary_engine import DictionaryEngine, normalize_bassa
from backend.config import settings
from backend.services import corpus as corpus_service

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False
    logger.warning(
        "sentence-transformers ou numpy manquant. "
        "Installez-les avec: pip install sentence-transformers numpy\n"
        "Le moteur ML se rabattra sur le dictionnaire."
    )


class MLEngine(TranslationEngine):
    """Moteur hybride : embeddings multilingues + dictionnaire en fallback.

    Le modèle paraphrase-multilingual-MiniLM-L12-v2 (~120 Mo) est téléchargé
    automatiquement par HuggingFace lors du premier démarrage, puis mis en cache
    localement. Il comprend nativement le français et l'anglais.

    Paramètres
    ----------
    dict_engine : DictionaryEngine | None
        Instance partagée du moteur dictionnaire. Si None, une nouvelle instance
        est créée. Passer l'instance existante évite de charger le dictionnaire
        en RAM plusieurs fois.
    """

    def __init__(self, dict_engine: DictionaryEngine | None = None):
        self._model = None
        self._embeddings = None          # np.ndarray (N, D) normalisé
        self._sources: list[str] = []    # textes sources du corpus
        self._bassa: list[str] = []      # traductions Bassa correspondantes
        self._langs: list[str] = []      # langues sources ("fr" / "en")

        # Si un moteur dictionnaire est fourni, on le partage (pas de double chargement).
        # _owns_dict_engine=False signifie que le rechargement est géré de l'extérieur.
        if dict_engine is not None:
            self._dict_engine = dict_engine
            self._owns_dict_engine = False
        else:
            self._dict_engine = DictionaryEngine()
            self._owns_dict_engine = True

        self._load_model()
        self.reload()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        if not _HAS_DEPS:
            return
        try:
            logger.info("Chargement du modèle d'embeddings : %s", settings.ML_EMBEDDING_MODEL)
            self._model = SentenceTransformer(settings.ML_EMBEDDING_MODEL)
            logger.info("Modèle d'embeddings chargé.")
        except Exception as exc:
            logger.error("Impossible de charger le modèle d'embeddings : %s", exc)
            self._model = None

    # ------------------------------------------------------------------
    # Reload (déclenché au démarrage et après chaque contribution approuvée)
    # ------------------------------------------------------------------

    def reload(self, db: Session = None) -> None:
        """Recharge le dictionnaire (si possédé) et reconstruit l'index d'embeddings du corpus."""
        if self._owns_dict_engine:
            self._dict_engine.reload(db)

        if self._model is None:
            return

        own_session = db is None
        if own_session:
            db = SessionLocal()

        try:
            # Seules les paires vérifiées alimentent l'index (cohérence avec LLMEngine)
            pairs = corpus_service.get_all_verified(db)
            if not pairs:
                logger.info("Corpus vide — index d'embeddings non construit.")
                self._embeddings = None
                return

            sources = [p.source_text for p in pairs]
            self._sources = sources
            self._bassa = [normalize_bassa(p.bassa_text) for p in pairs]
            self._langs = [p.source_language for p in pairs]

            logger.info("Encodage de %d paires du corpus...", len(sources))
            self._embeddings = self._model.encode(
                sources,
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True,   # cosine sim = simple produit scalaire
            )
            logger.info("Index ML prêt (%d vecteurs).", len(sources))
        finally:
            if own_session:
                db.close()

    # ------------------------------------------------------------------
    # Recherche de similarité
    # ------------------------------------------------------------------

    def _best_match(self, text: str, source_language: str) -> tuple[float, str, str]:
        """Retourne (score, source_matchée, traduction_bassa) pour la phrase la plus proche."""
        if self._model is None or self._embeddings is None:
            return 0.0, "", ""

        query = self._model.encode(
            [text],
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        # Produit scalaire = cosine (vecteurs normalisés).
        # flatten() garantit un tableau 1D même avec 1 seule paire corpus
        # (squeeze() retourne un scalaire 0-D dans ce cas, incompatible avec
        # l'indexation sur numpy ≥ 2.0).
        scores = (self._embeddings @ query.T).flatten()

        # Masque vectorisé : mise à -inf des entrées d'une autre langue,
        # puis argmax en une seule passe numpy (évite la boucle Python O(n)).
        lang_mask = np.array([l == source_language for l in self._langs])
        if not lang_mask.any():
            return 0.0, "", ""

        masked = np.where(lang_mask, scores, -np.inf)
        best_idx = int(np.argmax(masked))
        best_score = float(masked[best_idx])

        # best_score == -inf si toutes les langues sont filtrées (garde-fou)
        if not np.isfinite(best_score):
            return 0.0, "", ""

        return best_score, self._sources[best_idx], self._bassa[best_idx]

    # ------------------------------------------------------------------
    # Traduction
    # ------------------------------------------------------------------

    def translate(self, text: str, source_language: str) -> TranslationResult:
        if not text.strip():
            return TranslationResult(
                source_text=text,
                translated_text="",
                source_language=source_language,
                confidence=0.0,
                engine="ml",
            )

        score, matched_source, matched_bassa = self._best_match(text, source_language)

        # ---- Fallback dictionnaire (toujours calculé pour word_translations) ----
        dict_result = self._dict_engine.translate(text, source_language)

        # ---- Seuil haut : correspondance forte → traduction du corpus ----
        if score >= settings.ML_HIGH_THRESHOLD:
            warnings = []
            if matched_source.lower() != text.lower():
                warnings.append(
                    f"Traduction par similarité sémantique (score : {score:.0%}) — "
                    f"phrase de référence : « {matched_source} »"
                )
            return TranslationResult(
                source_text=text,
                translated_text=matched_bassa,
                source_language=source_language,
                confidence=round(score, 2),
                word_translations=dict_result.word_translations,
                warnings=warnings,
                engine="ml-retrieval",
            )

        # ---- Seuil moyen : suggérer la traduction du corpus en complément ----
        # On ignore les suggestions trop longues (versets bibliques, etc.)
        if score >= settings.ML_MED_THRESHOLD and len(matched_bassa) <= 150:
            preview = matched_bassa if len(matched_bassa) <= 80 else matched_bassa[:80] + "…"
            dict_result.warnings.append(
                f"Traduction similaire dans le corpus (score : {score:.0%}) : "
                f"« {preview} »"
            )
            dict_result.engine = "ml+dictionary"

        return dict_result

    # ------------------------------------------------------------------
    # Informations de diagnostic
    # ------------------------------------------------------------------

    @property
    def corpus_size(self) -> int:
        return len(self._sources)

    @property
    def model_ready(self) -> bool:
        return self._model is not None and self._embeddings is not None
