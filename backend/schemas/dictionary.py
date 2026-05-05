from pydantic import BaseModel


class ExampleBase(BaseModel):
    source_sentence: str
    bassa_sentence: str


class ExampleOut(ExampleBase):
    id: int
    model_config = {"from_attributes": True}


class DictionaryEntryCreate(BaseModel):
    source_language: str = "fr"
    source_word: str
    bassa_word: str
    phonetic: str | None = None
    category: str | None = None
    gender: str | None = None
    plural_form: str | None = None
    notes: str | None = None
    is_verified: bool = False
    examples: list[ExampleBase] = []


class DictionaryEntryUpdate(BaseModel):
    source_word: str | None = None
    bassa_word: str | None = None
    phonetic: str | None = None
    category: str | None = None
    gender: str | None = None
    plural_form: str | None = None
    notes: str | None = None
    is_verified: bool | None = None


class DictionaryEntryOut(BaseModel):
    id: int
    source_language: str
    source_word: str
    bassa_word: str
    phonetic: str | None
    category: str | None
    gender: str | None
    plural_form: str | None
    notes: str | None
    is_verified: bool
    examples: list[ExampleOut] = []

    model_config = {"from_attributes": True}


class DictionaryPage(BaseModel):
    items: list[DictionaryEntryOut]
    total: int
    page: int
    pages: int
