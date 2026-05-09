import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.contribution import Contribution, ContributionType, ContributionStatus
from backend.models.dictionary import DictionaryEntry
from backend.models.corpus import CorpusPair
from backend.models.user import User, UserRole
from backend.schemas.contribution import ContributionCreate, ContributionReview, ContributionOut, ContributionPage
from backend.services.auth_service import get_current_user, require_role

router = APIRouter(prefix="/api/contributions", tags=["contributions"])


@router.get("/stats")
def contribution_stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Résumé des contributions de l'utilisateur connecté (ou de tous pour admin/reviewer)."""
    q = db.query(Contribution)
    if user.role == UserRole.contributor:
        q = q.filter(Contribution.contributor_id == user.id)
    rows = q.all()
    counts = {"submitted": 0, "under_review": 0, "approved": 0, "rejected": 0, "total": len(rows)}
    for r in rows:
        status = r.status.value if hasattr(r.status, "value") else str(r.status)
        if status in counts:
            counts[status] += 1
    return counts


@router.get("", response_model=ContributionPage)
def list_contributions(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str = Query(None),
    type: str = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Contribution)
    # Non-admin users only see their own contributions
    if user.role == UserRole.contributor:
        q = q.filter(Contribution.contributor_id == user.id)
    if status:
        q = q.filter(Contribution.status == status)
    if type:
        q = q.filter(Contribution.type == type)

    total = q.count()
    items = q.order_by(Contribution.id.desc()).offset((page - 1) * size).limit(size).all()
    return ContributionPage(items=items, total=total, page=page, pages=math.ceil(total / size) if total else 1)


@router.post("", response_model=ContributionOut, status_code=201)
def create_contribution(
    data: ContributionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if data.type not in ("dictionary", "corpus"):
        raise HTTPException(status_code=400, detail="type must be 'dictionary' or 'corpus'")
    contribution = Contribution(
        contributor_id=user.id,
        type=data.type,
        source_language=data.source_language,
        source_text=data.source_text,
        bassa_text=data.bassa_text,
        category=data.category,
        notes=data.notes,
    )
    db.add(contribution)
    db.commit()
    db.refresh(contribution)
    return contribution


@router.put("/{contribution_id}/review", response_model=ContributionOut)
def review_contribution(
    contribution_id: int,
    data: ContributionReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.reviewer, UserRole.admin)),
):
    contribution = db.query(Contribution).filter(Contribution.id == contribution_id).first()
    if not contribution:
        raise HTTPException(status_code=404, detail="Contribution not found")
    if contribution.status != ContributionStatus.submitted:
        raise HTTPException(status_code=400, detail="Contribution already reviewed")

    if data.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be 'approved' or 'rejected'")

    contribution.status = data.status
    contribution.reviewer_id = user.id
    contribution.reviewer_comment = data.reviewer_comment
    contribution.reviewed_at = datetime.now(timezone.utc)

    # On approval, create the corresponding entry
    if data.status == "approved":
        if contribution.type == ContributionType.dictionary:
            entry = DictionaryEntry(
                source_language=contribution.source_language,
                source_word=contribution.source_text,
                bassa_word=contribution.bassa_text,
                category=contribution.category,
                notes=contribution.notes,
                is_verified=True,
            )
            db.add(entry)
        elif contribution.type == ContributionType.corpus:
            pair = CorpusPair(
                source_language=contribution.source_language,
                source_text=contribution.source_text,
                bassa_text=contribution.bassa_text,
                is_verified=True,
            )
            db.add(pair)

    db.commit()
    db.refresh(contribution)

    # Recharger tous les moteurs avec la session courante pour que
    # l'entrée nouvellement committée soit immédiatement visible
    # dans le dictionnaire et l'index ML.
    if data.status == "approved":
        from backend.api import translate as translate_mod
        for engine in translate_mod._engines.values():
            try:
                engine.reload(db)
            except Exception:
                pass

    return contribution
