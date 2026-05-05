"""Service centralisé pour l'accès et l'import du corpus parallèle Bassa.

Utilisé par :
  - MLEngine.reload()   → get_all_verified()
  - LLMEngine.reload()  → get_all_verified()
  - api/corpus.py       → import_csv()
"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.models.corpus import CorpusPair

logger = logging.getLogger(__name__)

# Colonnes attendues dans le CSV d'import (order-insensitive)
_REQUIRED_CSV_COLS = {"source_language", "source_text", "bassa_text"}
_OPTIONAL_CSV_COLS = {"domain", "source_reference", "is_verified"}


@dataclass
class ImportResult:
    imported: int
    skipped: int
    errors: list[str]


def get_all_verified(db: Session, lang: str | None = None) -> list[CorpusPair]:
    """Retourne les paires de corpus vérifiées, optionnellement filtrées par langue."""
    q = db.query(CorpusPair).filter(CorpusPair.is_verified == True)  # noqa: E712
    if lang:
        q = q.filter(CorpusPair.source_language == lang)
    return q.all()


def get_all(db: Session, lang: str | None = None) -> list[CorpusPair]:
    """Retourne toutes les paires de corpus (vérifiées et non vérifiées)."""
    q = db.query(CorpusPair)
    if lang:
        q = q.filter(CorpusPair.source_language == lang)
    return q.all()


def import_csv(
    db: Session,
    content: str | bytes,
    default_lang: str = "fr",
    verified: bool = True,
) -> ImportResult:
    """Importe des paires de corpus depuis un contenu CSV.

    Paramètres
    ----------
    db : Session
        Session SQLAlchemy active (commit réalisé par l'appelant).
    content : str | bytes
        Contenu du fichier CSV (UTF-8).
    default_lang : str
        Langue source utilisée si la colonne source_language est absente.
    verified : bool
        Marque les paires importées comme vérifiées.

    Format CSV attendu (séparateur virgule, première ligne = en-têtes) :
        source_language,source_text,bassa_text[,domain,source_reference,is_verified]

    Retourne un ImportResult avec les compteurs.
    """
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")  # gère le BOM éventuel

    reader = csv.DictReader(io.StringIO(content))

    if reader.fieldnames is None:
        return ImportResult(imported=0, skipped=0, errors=["Fichier CSV vide ou sans en-têtes"])

    cols = {c.strip().lower() for c in reader.fieldnames}
    missing = _REQUIRED_CSV_COLS - {"source_language"} - cols  # source_language est optionnelle
    if "source_text" not in cols or "bassa_text" not in cols:
        return ImportResult(
            imported=0,
            skipped=0,
            errors=[f"Colonnes requises manquantes : {missing | (_REQUIRED_CSV_COLS - {'source_language'} - cols)}"],
        )

    imported = 0
    skipped = 0
    errors: list[str] = []

    for i, row in enumerate(reader, start=2):  # start=2 car ligne 1 = en-têtes
        source_text = (row.get("source_text") or "").strip()
        bassa_text = (row.get("bassa_text") or "").strip()

        if not source_text or not bassa_text:
            skipped += 1
            continue

        lang = (row.get("source_language") or default_lang).strip().lower()
        if lang not in ("fr", "en"):
            errors.append(f"Ligne {i} : langue '{lang}' invalide (fr/en attendu) — ignorée")
            skipped += 1
            continue

        # Vérifier les doublons (même source_language + source_text)
        exists = (
            db.query(CorpusPair.id)
            .filter(
                CorpusPair.source_language == lang,
                CorpusPair.source_text == source_text,
            )
            .first()
        )
        if exists:
            skipped += 1
            continue

        # Lire les colonnes optionnelles
        domain = (row.get("domain") or "").strip() or None
        source_ref = (row.get("source_reference") or "").strip() or None

        # La colonne is_verified du CSV peut surcharger le paramètre par défaut
        csv_verified_str = (row.get("is_verified") or "").strip().lower()
        if csv_verified_str in ("1", "true", "yes", "oui"):
            row_verified = True
        elif csv_verified_str in ("0", "false", "no", "non"):
            row_verified = False
        else:
            row_verified = verified

        pair = CorpusPair(
            source_language=lang,
            source_text=source_text,
            bassa_text=bassa_text,
            domain=domain,
            source_reference=source_ref,
            is_verified=row_verified,
        )
        db.add(pair)
        imported += 1

    logger.info("Import CSV corpus : %d importées, %d ignorées, %d erreurs", imported, skipped, len(errors))
    return ImportResult(imported=imported, skipped=skipped, errors=errors)
