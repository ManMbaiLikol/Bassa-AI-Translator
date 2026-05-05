from typing import Literal

from pydantic import BaseModel


class TranslateRequest(BaseModel):
    text: str
    source_language: str = "fr"  # fr or en
    # Permet de choisir le moteur par requête ; None = moteur par défaut du serveur
    engine_type: Literal["dictionary", "ml", "llm", "nmt"] | None = None


class WordTranslationOut(BaseModel):
    source: str
    translated: str
    found: bool


class TranslateResponse(BaseModel):
    source_text: str
    translated_text: str
    source_language: str
    confidence: float
    word_translations: list[WordTranslationOut]
    warnings: list[str]
    engine: str
    history_id: int | None = None


class TranslateFeedback(BaseModel):
    history_id: int
    corrected_text: str | None = None  # texte Bassa corrigé par l'utilisateur
    add_to_corpus: bool = False        # True = ajouter au corpus (en attente de validation)
