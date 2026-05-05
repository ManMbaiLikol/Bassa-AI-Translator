"""Statistiques publiques et d'activité.

- GET /api/stats            — stats globales publiques
- GET /api/stats/activity   — activité des N derniers jours (admin)
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.history import TranslationHistory
from backend.models.dictionary import DictionaryEntry
from backend.models.corpus import CorpusPair
from backend.models.contribution import Contribution, ContributionStatus
from backend.models.user import UserRole
from backend.services.auth_service import require_role

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def global_stats(db: Session = Depends(get_db)):
    """Statistiques publiques de l'application."""
    total_translations = db.query(TranslationHistory).count()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_translations = db.query(TranslationHistory).filter(
        TranslationHistory.created_at >= today_start
    ).count()

    # Répartition par moteur
    engine_rows = (
        db.query(TranslationHistory.engine, func.count(TranslationHistory.id))
        .group_by(TranslationHistory.engine)
        .all()
    )
    by_engine = {row[0]: row[1] for row in engine_rows}

    # Répartition par langue
    lang_rows = (
        db.query(TranslationHistory.source_language, func.count(TranslationHistory.id))
        .group_by(TranslationHistory.source_language)
        .all()
    )
    by_language = {row[0]: row[1] for row in lang_rows}

    return {
        "translations": {
            "total": total_translations,
            "today": today_translations,
            "by_engine": by_engine,
            "by_language": by_language,
        },
        "dictionary": {
            "total": db.query(DictionaryEntry).count(),
            "verified": db.query(DictionaryEntry).filter(DictionaryEntry.is_verified == True).count(),
        },
        "corpus": {
            "total": db.query(CorpusPair).count(),
            "verified": db.query(CorpusPair).filter(CorpusPair.is_verified == True).count(),
        },
        "contributions": {
            "pending": db.query(Contribution).filter(
                Contribution.status == ContributionStatus.submitted
            ).count(),
        },
    }


@router.get("/activity")
def activity(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.admin)),
):
    """Activité des N derniers jours (admin uniquement).

    Retourne le nombre de traductions par jour et la répartition par moteur.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Traductions par jour
    rows = (
        db.query(
            func.date(TranslationHistory.created_at).label("day"),
            func.count(TranslationHistory.id).label("count"),
        )
        .filter(TranslationHistory.created_at >= since)
        .group_by(func.date(TranslationHistory.created_at))
        .order_by(func.date(TranslationHistory.created_at))
        .all()
    )
    translations_per_day = [{"date": str(r.day), "count": r.count} for r in rows]

    # Top moteurs sur la période
    engine_rows = (
        db.query(TranslationHistory.engine, func.count(TranslationHistory.id).label("count"))
        .filter(TranslationHistory.created_at >= since)
        .group_by(TranslationHistory.engine)
        .order_by(func.count(TranslationHistory.id).desc())
        .all()
    )
    top_engines = [{"engine": r.engine, "count": r.count} for r in engine_rows]

    # Confiance moyenne par moteur
    conf_rows = (
        db.query(
            TranslationHistory.engine,
            func.avg(TranslationHistory.confidence).label("avg_confidence"),
        )
        .filter(TranslationHistory.created_at >= since, TranslationHistory.confidence.isnot(None))
        .group_by(TranslationHistory.engine)
        .all()
    )
    avg_confidence = {
        r.engine: round(float(r.avg_confidence), 3) for r in conf_rows
    }

    return {
        "period_days": days,
        "translations_per_day": translations_per_day,
        "top_engines": top_engines,
        "avg_confidence_by_engine": avg_confidence,
    }
