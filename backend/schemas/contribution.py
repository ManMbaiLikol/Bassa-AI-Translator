from pydantic import BaseModel


class ContributionCreate(BaseModel):
    type: str  # "dictionary" or "corpus"
    source_language: str = "fr"
    source_text: str
    bassa_text: str
    category: str | None = None
    notes: str | None = None


class ContributionReview(BaseModel):
    status: str  # "approved" or "rejected"
    reviewer_comment: str | None = None


class ContributionOut(BaseModel):
    id: int
    contributor_id: int
    type: str
    status: str
    source_language: str
    source_text: str
    bassa_text: str
    category: str | None
    notes: str | None
    reviewer_id: int | None
    reviewer_comment: str | None

    model_config = {"from_attributes": True}


class ContributionPage(BaseModel):
    items: list[ContributionOut]
    total: int
    page: int
    pages: int
