import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models.dictionary import DictionaryEntry, DictionaryExample
from backend.models.user import UserRole
from backend.schemas.dictionary import (
    DictionaryEntryCreate, DictionaryEntryUpdate, DictionaryEntryOut, DictionaryPage, ExampleBase,
)
from backend.services.auth_service import require_role, get_optional_user
from backend.services.tonal import strip_tones

router = APIRouter(prefix="/api/dictionary", tags=["dictionary"])


@router.get("", response_model=DictionaryPage)
def list_entries(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    lang: str = Query(None),
    category: str = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(DictionaryEntry).options(joinedload(DictionaryEntry.examples))
    if search:
        # Match against source_word, bassa_word, AND the tonal-stripped
        # bassa_word_normalized so users can search "nyo" and find "nyó".
        search_norm = strip_tones(search).lower()
        q = q.filter(
            DictionaryEntry.source_word.ilike(f"%{search}%")
            | DictionaryEntry.bassa_word.ilike(f"%{search}%")
            | DictionaryEntry.bassa_word_normalized.ilike(f"%{search_norm}%")
        )
    if lang:
        q = q.filter(DictionaryEntry.source_language == lang)
    if category:
        q = q.filter(DictionaryEntry.category == category)

    total = q.count()
    items = q.order_by(DictionaryEntry.source_word).offset((page - 1) * size).limit(size).all()
    # Deduplicate due to joinedload + pagination
    seen = set()
    unique = []
    for item in items:
        if item.id not in seen:
            seen.add(item.id)
            unique.append(item)
    return DictionaryPage(items=unique, total=total, page=page, pages=math.ceil(total / size) if total else 1)


@router.get("/{entry_id}", response_model=DictionaryEntryOut)
def get_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(DictionaryEntry).options(joinedload(DictionaryEntry.examples)).filter(DictionaryEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


@router.post("", response_model=DictionaryEntryOut, status_code=201)
def create_entry(
    data: DictionaryEntryCreate,
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.reviewer, UserRole.admin)),
):
    entry = DictionaryEntry(
        source_language=data.source_language,
        source_word=data.source_word,
        bassa_word=data.bassa_word,
        phonetic=data.phonetic,
        category=data.category,
        gender=data.gender,
        plural_form=data.plural_form,
        notes=data.notes,
        is_verified=data.is_verified,
    )
    db.add(entry)
    db.flush()
    for ex in data.examples:
        db.add(DictionaryExample(entry_id=entry.id, source_sentence=ex.source_sentence, bassa_sentence=ex.bassa_sentence))
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=DictionaryEntryOut)
def update_entry(
    entry_id: int,
    data: DictionaryEntryUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.reviewer, UserRole.admin)),
):
    entry = db.query(DictionaryEntry).filter(DictionaryEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.admin)),
):
    entry = db.query(DictionaryEntry).filter(DictionaryEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()


@router.post("/{entry_id}/examples", response_model=DictionaryEntryOut)
def add_example(
    entry_id: int,
    data: ExampleBase,
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.reviewer, UserRole.admin)),
):
    entry = db.query(DictionaryEntry).filter(DictionaryEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.add(DictionaryExample(entry_id=entry_id, source_sentence=data.source_sentence, bassa_sentence=data.bassa_sentence))
    db.commit()
    db.refresh(entry)
    return entry
