from pydantic import BaseModel


class CorpusPairCreate(BaseModel):
    source_language: str = "fr"
    source_text: str
    bassa_text: str
    domain: str | None = None
    source_reference: str | None = None
    is_verified: bool = False


class CorpusPairUpdate(BaseModel):
    source_text: str | None = None
    bassa_text: str | None = None
    domain: str | None = None
    source_reference: str | None = None
    is_verified: bool | None = None


class CorpusPairOut(BaseModel):
    id: int
    source_language: str
    source_text: str
    bassa_text: str
    domain: str | None
    source_reference: str | None
    is_verified: bool

    model_config = {"from_attributes": True}


class CorpusPage(BaseModel):
    items: list[CorpusPairOut]
    total: int
    page: int
    pages: int
