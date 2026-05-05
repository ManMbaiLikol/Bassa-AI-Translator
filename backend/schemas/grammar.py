from pydantic import BaseModel, Field


class GrammaticalRuleCreate(BaseModel):
    rule_name: str = Field(..., min_length=2, max_length=255)
    source_language: str = Field(..., pattern="^(fr|en)$")
    pattern: str = Field(..., min_length=1)
    transformation: str
    priority: int = 0
    is_active: bool = True


class GrammaticalRuleUpdate(BaseModel):
    rule_name: str | None = None
    pattern: str | None = None
    transformation: str | None = None
    is_active: bool | None = None
    priority: int | None = None


class GrammaticalRuleOut(BaseModel):
    id: int
    rule_name: str
    source_language: str
    pattern: str
    transformation: str
    priority: int
    is_active: bool

    model_config = {"from_attributes": True}
