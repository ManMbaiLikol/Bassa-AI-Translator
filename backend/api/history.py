"""Historique des traductions.

- GET  /api/history          — liste paginée (utilisateur : les siennes ; admin : toutes)
- DELETE /api/history        — vider son historique
- DELETE /api/history/{id}   — supprimer une entrée
- GET  /api/history/export   — export CSV de son historique
"""
import csv
import io
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.history import TranslationHistory
from backend.models.user import User, UserRole
from backend.schemas.history import HistoryEntryOut, HistoryPage
from backend.services.auth_service import get_current_user

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=HistoryPage)
def list_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    lang: str = Query(None),
    engine: str = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Historique paginé.

    - Utilisateur standard : uniquement ses propres traductions.
    - Admin : toutes les traductions (filtre user_id optionnel via query param).
    """
    q = db.query(TranslationHistory)

    if user.role != UserRole.admin:
        q = q.filter(TranslationHistory.user_id == user.id)

    if lang:
        q = q.filter(TranslationHistory.source_language == lang)
    if engine:
        q = q.filter(TranslationHistory.engine == engine)

    total = q.count()
    items = q.order_by(TranslationHistory.created_at.desc()).offset((page - 1) * size).limit(size).all()
    return HistoryPage(
        items=items,
        total=total,
        page=page,
        pages=math.ceil(total / size) if total else 1,
    )


@router.delete("", status_code=204)
def clear_history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Supprime tout l'historique de l'utilisateur connecté."""
    db.query(TranslationHistory).filter(TranslationHistory.user_id == user.id).delete()
    db.commit()


@router.delete("/{entry_id}", status_code=204)
def delete_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Supprime une entrée d'historique (propriétaire ou admin)."""
    entry = db.query(TranslationHistory).filter(TranslationHistory.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.user_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Not allowed")
    db.delete(entry)
    db.commit()


@router.get("/export")
def export_history(
    lang: str = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Export CSV de l'historique de l'utilisateur connecté."""
    q = db.query(TranslationHistory).filter(TranslationHistory.user_id == user.id)
    if lang:
        q = q.filter(TranslationHistory.source_language == lang)
    entries = q.order_by(TranslationHistory.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "source_language", "source_text", "translated_text", "engine", "confidence", "created_at"])
    for e in entries:
        writer.writerow([
            e.id, e.source_language, e.source_text, e.translated_text,
            e.engine, e.confidence, e.created_at.isoformat() if e.created_at else "",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=history_export.csv"},
    )
