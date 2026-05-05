import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.rate_limit import limiter, _auth_key, _translate_limit

logger = logging.getLogger(__name__)

from backend.database import get_db
from backend.models.history import TranslationHistory
from backend.models.user import User, UserRole
from backend.schemas.translate import TranslateRequest, TranslateResponse, TranslateFeedback
from backend.engine.base import TranslationEngine
from backend.services.auth_service import get_optional_user, require_role

router = APIRouter(prefix="/api", tags=["translate"])

# Registre des moteurs disponibles et moteur par défaut
_engines: dict[str, TranslationEngine] = {}
_default_engine_type: str = "dictionary"


def register_engine(engine_type: str, engine: TranslationEngine) -> None:
    """Enregistre un moteur de traduction sous un nom donné."""
    _engines[engine_type] = engine


def set_default_engine(engine_type: str) -> None:
    """Définit le moteur utilisé quand la requête ne précise pas engine_type."""
    global _default_engine_type
    _default_engine_type = engine_type


def get_engine(engine_type: str | None = None) -> TranslationEngine:
    """Retourne le moteur demandé, ou le moteur par défaut."""
    key = engine_type or _default_engine_type
    engine = _engines.get(key)
    if engine is None:
        # Dernier recours : premier moteur enregistré
        engine = next(iter(_engines.values()), None)
    return engine


@router.post("/translate", response_model=TranslateResponse)
@limiter.limit(_translate_limit, key_func=_auth_key)
def translate(
    request: Request,
    data: TranslateRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    if not _engines:
        raise HTTPException(status_code=503, detail="Aucun moteur de traduction initialisé")
    if data.source_language not in ("fr", "en"):
        raise HTTPException(status_code=400, detail="source_language doit être 'fr' ou 'en'")
    if not data.text.strip():
        raise HTTPException(status_code=400, detail="Le texte ne peut pas être vide")
    if len(data.text) > 5000:
        raise HTTPException(status_code=400, detail="Texte trop long (max 5000 caractères)")

    engine = get_engine(data.engine_type)
    if engine is None:
        raise HTTPException(status_code=503, detail="Moteur de traduction introuvable")

    result = engine.translate(data.text, data.source_language)

    # Enregistrer dans l'historique (utilisateur connecté ou anonyme).
    # db.flush() déclenche l'INSERT et populé entry.id sans ouvrir une transaction
    # supplémentaire ; db.commit() finalise. On évite ainsi db.refresh() qui ferait
    # un SELECT inutile juste pour récupérer l'id.
    entry = TranslationHistory(
        user_id=user.id if user else None,
        source_language=result.source_language,
        source_text=result.source_text,
        translated_text=result.translated_text,
        engine=result.engine,
        confidence=result.confidence if result.confidence > 0 else None,
    )
    db.add(entry)
    db.flush()
    history_id = entry.id
    db.commit()

    return TranslateResponse(
        source_text=result.source_text,
        translated_text=result.translated_text,
        source_language=result.source_language,
        confidence=result.confidence,
        word_translations=[
            {"source": w.source, "translated": w.translated, "found": w.found}
            for w in result.word_translations
        ],
        warnings=result.warnings,
        engine=result.engine,
        history_id=history_id,
    )


def _do_reload():
    """Recharge tous les moteurs en arrière-plan."""
    for engine_type, engine in _engines.items():
        try:
            engine.reload()
            logger.info("Moteur '%s' rechargé avec succès.", engine_type)
        except Exception as exc:
            logger.error("Erreur rechargement moteur '%s': %s", engine_type, exc)


@router.post("/translate/reload")
def reload_engines(
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role(UserRole.reviewer, UserRole.admin)),
):
    """Lance le rechargement de tous les moteurs en arrière-plan. Nécessite reviewer+."""
    if not _engines:
        raise HTTPException(status_code=503, detail="Aucun moteur de traduction initialisé")
    background_tasks.add_task(_do_reload)
    return {
        "status": "accepted",
        "message": "Rechargement lancé en arrière-plan",
        "engines": list(_engines.keys()),
    }


@router.post("/translate/feedback")
def translate_feedback(
    data: TranslateFeedback,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """Feedback sur une traduction.

    - Si add_to_corpus=True : ajoute la traduction (ou la correction) au corpus
      en statut non-vérifié, pour relecture par un reviewer.
    - corrected_text : texte Bassa corrigé par l'utilisateur (optionnel).
    """
    from backend.models.corpus import CorpusPair

    history = db.query(TranslationHistory).filter(TranslationHistory.id == data.history_id).first()
    if not history:
        raise HTTPException(status_code=404, detail="Traduction introuvable")

    if not data.add_to_corpus:
        return {"status": "ok"}

    if not user:
        raise HTTPException(status_code=401, detail="Connexion requise pour contribuer au corpus")

    # Vérifier doublon
    exists = db.query(CorpusPair).filter(
        CorpusPair.source_language == history.source_language,
        CorpusPair.source_text == history.source_text,
    ).first()
    if exists:
        return {"status": "already_exists", "pair_id": exists.id}

    bassa_text = data.corrected_text.strip() if data.corrected_text else history.translated_text
    pair = CorpusPair(
        source_language=history.source_language,
        source_text=history.source_text,
        bassa_text=bassa_text,
        is_verified=False,
    )
    db.add(pair)
    db.commit()
    db.refresh(pair)

    return {"status": "added", "pair_id": pair.id}


@router.get("/translate/engines")
def list_engines():
    """Liste les moteurs disponibles et le moteur par défaut."""
    return {
        "default": _default_engine_type,
        "available": list(_engines.keys()),
    }
