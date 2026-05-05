import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.api import auth, dictionary, translate, corpus, contributions, admin, history, stats
from backend.rate_limit import limiter
from backend.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


def _build_engines() -> dict:
    """Instancie et retourne les moteurs de traduction selon la configuration.

    Stratégie "auto" :
      - Si ANTHROPIC_API_KEY est renseignée → LLM (avec ML comme fallback si dispo)
      - Sinon si sentence-transformers est installé → ML
      - Sinon → Dictionary

    Les moteurs "dictionary" et "ml" sont toujours construits pour servir
    de fallback et pour permettre la sélection par requête (engine_type).
    """
    engines = {}

    # ---- Moteur dictionnaire (toujours disponible) ----
    from backend.engine.dictionary_engine import DictionaryEngine
    engines["dictionary"] = DictionaryEngine()
    logger.info("Moteur 'dictionary' initialisé.")

    # ---- Moteur ML (si sentence-transformers est installé) ----
    try:
        from backend.engine.ml_engine import MLEngine, _HAS_DEPS as ml_deps
        if ml_deps:
            # On passe l'instance dictionnaire partagée pour éviter un double chargement en RAM
            ml_engine = MLEngine(dict_engine=engines["dictionary"])
            engines["ml"] = ml_engine
            logger.info(
                "Moteur 'ml' initialisé — corpus : %d paires, modèle prêt : %s",
                ml_engine.corpus_size,
                ml_engine.model_ready,
            )
        else:
            logger.warning("Moteur ML désactivé : dépendances manquantes (sentence-transformers / numpy).")
            ml_engine = None
    except Exception as exc:
        logger.error("Erreur lors de l'initialisation du moteur ML : %s", exc)
        ml_engine = None

    # ---- Moteur NMT (si modèle entraîné présent) ----
    try:
        from backend.engine.nmt_engine import NMTEngine, _HAS_DEPS as nmt_deps
        if nmt_deps:
            nmt_engine = NMTEngine(model_dir=settings.NMT_MODEL_DIR or None)
            if nmt_engine.model_ready:
                engines["nmt"] = nmt_engine
                logger.info("Moteur 'nmt' (MarianMT fine-tuné) initialisé.")
            else:
                logger.info(
                    "Moteur NMT disponible mais modèle non encore entraîné. "
                    "Lancez : python scripts/train_nmt.py"
                )
        else:
            logger.warning("Moteur NMT désactivé : transformers/torch manquants.")
    except Exception as exc:
        logger.error("Erreur lors de l'initialisation du moteur NMT : %s", exc)

    # ---- Moteur LLM (si clé API fournie) ----
    if settings.ANTHROPIC_API_KEY:
        try:
            from backend.engine.llm_engine import LLMEngine, _HAS_ANTHROPIC
            if _HAS_ANTHROPIC:
                engines["llm"] = LLMEngine(
                    api_key=settings.ANTHROPIC_API_KEY,
                    fallback_engine=ml_engine or engines["dictionary"],
                    # Instance partagée : le dictionnaire n'est chargé qu'une seule fois
                    dict_engine=engines["dictionary"],
                )
                logger.info("Moteur 'llm' (Claude) initialisé.")
            else:
                logger.warning("Moteur LLM désactivé : package 'anthropic' manquant.")
        except Exception as exc:
            logger.error("Erreur lors de l'initialisation du moteur LLM : %s", exc)
    else:
        logger.info("ANTHROPIC_API_KEY non renseignée — moteur LLM désactivé.")

    return engines


def _choose_default(engines: dict) -> str:
    """Choisit le moteur par défaut selon ENGINE_TYPE et ce qui est disponible."""
    requested = settings.ENGINE_TYPE.lower()

    if requested == "auto":
        if "llm" in engines:
            return "llm"
        if "nmt" in engines:
            return "nmt"
        if "ml" in engines:
            return "ml"
        return "dictionary"

    if requested in engines:
        return requested

    logger.warning(
        "Moteur '%s' demandé mais non disponible. Fallback sur 'dictionary'.", requested
    )
    return "dictionary"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrage : construction et enregistrement des moteurs
    engines = _build_engines()
    for engine_type, engine in engines.items():
        translate.register_engine(engine_type, engine)

    default = _choose_default(engines)
    translate.set_default_engine(default)
    logger.info(
        "Moteurs disponibles : %s | Moteur par défaut : %s",
        list(engines.keys()),
        default,
    )
    yield
    # Arrêt : rien à nettoyer pour l'instant


app = FastAPI(
    title="BassaAI Translator",
    description="Traduction automatique FR/EN vers Bassa — moteurs : dictionary, ml, llm",
    version="2.0.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS — origines lues depuis ALLOWED_ORIGINS (.env)
_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Health check (Railway / Docker)
@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok"}

# Routes API
app.include_router(auth.router)
app.include_router(translate.router)
app.include_router(history.router)
app.include_router(stats.router)
app.include_router(dictionary.router)
app.include_router(corpus.router)
app.include_router(contributions.router)
app.include_router(admin.router)

# Frontend statique
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir / "static")), name="static")
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
