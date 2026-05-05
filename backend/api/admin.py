from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.user import User, UserRole
from backend.models.dictionary import DictionaryEntry
from backend.models.corpus import CorpusPair
from backend.models.contribution import Contribution, ContributionStatus
from backend.models.grammar import GrammaticalRule
from backend.services.auth_service import require_role
from backend.schemas.auth import UserOutAdmin
from backend.schemas.grammar import GrammaticalRuleCreate, GrammaticalRuleUpdate, GrammaticalRuleOut

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats")
def admin_stats(
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.admin, UserRole.reviewer)),
):
    return {
        "users": db.query(User).count(),
        "dictionary_entries": db.query(DictionaryEntry).count(),
        "dictionary_verified": db.query(DictionaryEntry).filter(DictionaryEntry.is_verified == True).count(),
        "corpus_pairs": db.query(CorpusPair).count(),
        "corpus_verified": db.query(CorpusPair).filter(CorpusPair.is_verified == True).count(),
        "contributions_total": db.query(Contribution).count(),
        "contributions_pending": db.query(Contribution).filter(Contribution.status == ContributionStatus.submitted).count(),
        "grammar_rules": db.query(GrammaticalRule).count(),
    }


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.admin)),
):
    users = db.query(User).order_by(User.id).all()
    return [UserOutAdmin.model_validate(u) for u in users]


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.admin)),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Impossible de supprimer son propre compte")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(target)
    db.commit()


@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    role: str = Query(...),
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.admin)),
):
    if role not in ("contributor", "reviewer", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.role = role
    db.commit()
    return {"status": "ok", "user_id": user_id, "new_role": role}


@router.get("/rules", response_model=list[GrammaticalRuleOut])
def list_rules(
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.admin, UserRole.reviewer)),
):
    return db.query(GrammaticalRule).order_by(GrammaticalRule.priority, GrammaticalRule.id).all()


@router.post("/rules", response_model=GrammaticalRuleOut, status_code=201)
def create_rule(
    payload: GrammaticalRuleCreate,
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.admin)),
):
    rule = GrammaticalRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    _trigger_reload(db)
    return rule


@router.put("/rules/{rule_id}", response_model=GrammaticalRuleOut)
def update_rule(
    rule_id: int,
    payload: GrammaticalRuleUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.admin)),
):
    rule = db.query(GrammaticalRule).filter(GrammaticalRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    _trigger_reload(db)
    return rule


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.admin)),
):
    rule = db.query(GrammaticalRule).filter(GrammaticalRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    _trigger_reload(db)


def _trigger_reload(db: Session):
    """Recharge tous les moteurs après une modification de règle grammaticale."""
    try:
        from backend.api import translate as translate_mod
        for engine in translate_mod._engines.values():
            engine.reload(db)
    except Exception:
        pass
