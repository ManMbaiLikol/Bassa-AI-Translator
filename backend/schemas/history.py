from datetime import datetime
from pydantic import BaseModel


class HistoryEntryOut(BaseModel):
    id: int
    user_id: int | None
    source_language: str
    source_text: str
    translated_text: str
    engine: str
    confidence: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class HistoryPage(BaseModel):
    items: list[HistoryEntryOut]
    total: int
    page: int
    pages: int
