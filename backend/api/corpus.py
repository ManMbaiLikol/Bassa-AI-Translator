import csv
import io
import math

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.corpus import CorpusPair
from backend.models.user import UserRole
from backend.schemas.corpus import CorpusPairCreate, CorpusPairUpdate, CorpusPairOut, CorpusPage
from backend.services.auth_service import require_role
from backend.services import corpus as corpus_service

router = APIRouter(prefix="/api/corpus", tags=["corpus"])


@router.get("", response_model=CorpusPage)
def list_pairs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    lang: str = Query(None),
    domain: str = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(CorpusPair)
    if search:
        q = q.filter(
            CorpusPair.source_text.ilike(f"%{search}%")
            | CorpusPair.bassa_text.ilike(f"%{search}%")
        )
    if lang:
        q = q.filter(CorpusPair.source_language == lang)
    if domain:
        q = q.filter(CorpusPair.domain == domain)

    total = q.count()
    items = q.order_by(CorpusPair.id.desc()).offset((page - 1) * size).limit(size).all()
    return CorpusPage(items=items, total=total, page=page, pages=math.ceil(total / size) if total else 1)


@router.get("/export")
def export_csv(lang: str = Query(None), db: Session = Depends(get_db)):
    q = db.query(CorpusPair)
    if lang:
        q = q.filter(CorpusPair.source_language == lang)
    pairs = q.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "source_language", "source_text", "bassa_text", "domain", "source_reference", "is_verified"])
    for p in pairs:
        writer.writerow([p.id, p.source_language, p.source_text, p.bassa_text, p.domain, p.source_reference, p.is_verified])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=corpus_export.csv"},
    )


@router.get("/stats")
def corpus_stats(db: Session = Depends(get_db)):
    total = db.query(CorpusPair).count()
    verified = db.query(CorpusPair).filter(CorpusPair.is_verified == True).count()
    fr_count = db.query(CorpusPair).filter(CorpusPair.source_language == "fr").count()
    en_count = db.query(CorpusPair).filter(CorpusPair.source_language == "en").count()
    return {"total": total, "verified": verified, "fr": fr_count, "en": en_count}


@router.get("/{pair_id}", response_model=CorpusPairOut)
def get_pair(pair_id: int, db: Session = Depends(get_db)):
    pair = db.query(CorpusPair).filter(CorpusPair.id == pair_id).first()
    if not pair:
        raise HTTPException(status_code=404, detail="Corpus pair not found")
    return pair


@router.post("", response_model=CorpusPairOut, status_code=201)
def create_pair(
    data: CorpusPairCreate,
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.reviewer, UserRole.admin)),
):
    pair = CorpusPair(**data.model_dump())
    db.add(pair)
    db.commit()
    db.refresh(pair)
    return pair


@router.put("/{pair_id}", response_model=CorpusPairOut)
def update_pair(
    pair_id: int,
    data: CorpusPairUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.reviewer, UserRole.admin)),
):
    pair = db.query(CorpusPair).filter(CorpusPair.id == pair_id).first()
    if not pair:
        raise HTTPException(status_code=404, detail="Corpus pair not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(pair, field, value)
    db.commit()
    db.refresh(pair)
    return pair


@router.delete("/{pair_id}", status_code=204)
def delete_pair(
    pair_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.admin)),
):
    pair = db.query(CorpusPair).filter(CorpusPair.id == pair_id).first()
    if not pair:
        raise HTTPException(status_code=404, detail="Corpus pair not found")
    db.delete(pair)
    db.commit()


@router.post("/import")
async def import_csv(
    file: UploadFile = File(..., description="Fichier CSV UTF-8 : source_language,source_text,bassa_text[,domain,source_reference,is_verified]"),
    lang: str = Query("fr", description="Langue source par défaut si la colonne source_language est absente"),
    verified: bool = Query(True, description="Marquer les paires importées comme vérifiées"),
    db: Session = Depends(get_db),
    user=Depends(require_role(UserRole.admin)),
):
    """Import en masse de paires corpus depuis un fichier CSV (admin uniquement).

    - Colonnes requises : `source_text`, `bassa_text`
    - Colonnes optionnelles : `source_language` (défaut = paramètre `lang`),
      `domain`, `source_reference`, `is_verified`
    - Les doublons (même langue + source_text) sont automatiquement ignorés.
    - Après import, recharge tous les moteurs de traduction.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Le fichier doit être un CSV (.csv)")

    if lang not in ("fr", "en"):
        raise HTTPException(status_code=400, detail="lang doit être 'fr' ou 'en'")

    content = await file.read()
    result = corpus_service.import_csv(db, content, default_lang=lang, verified=verified)

    if result.imported > 0:
        db.commit()
        # Recharger les moteurs pour que l'index ML intègre les nouvelles paires
        from backend.api import translate as translate_mod
        for engine in translate_mod._engines.values():
            try:
                engine.reload(db)
            except Exception:
                pass
    else:
        db.rollback()

    return {
        "imported": result.imported,
        "skipped": result.skipped,
        "errors": result.errors,
    }
