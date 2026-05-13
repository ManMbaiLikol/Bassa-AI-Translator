from sqlalchemy import Column, Integer, String, Boolean, Text, ForeignKey, DateTime, event, func
from sqlalchemy.orm import relationship

from backend.database import Base
from backend.services.tonal import strip_tones


class DictionaryEntry(Base):
    __tablename__ = "dictionary_entries"

    id = Column(Integer, primary_key=True, index=True)
    source_language = Column(String(2), nullable=False, index=True)  # fr or en
    source_word = Column(String(191), nullable=False, index=True)
    bassa_word = Column(String(255), nullable=False)
    bassa_word_normalized = Column(String(255), nullable=True, index=True)
    phonetic = Column(String(255), nullable=True)
    category = Column(String(50), nullable=True)  # noun, verb, adjective, etc.
    gender = Column(String(20), nullable=True)
    plural_form = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    examples = relationship("DictionaryExample", back_populates="entry", cascade="all, delete-orphan")


def _refresh_normalized(target: "DictionaryEntry") -> None:
    target.bassa_word_normalized = strip_tones(target.bassa_word or "").lower() or None


@event.listens_for(DictionaryEntry, "before_insert")
def _set_normalized_on_insert(_mapper, _connection, target):  # type: ignore[no-untyped-def]
    _refresh_normalized(target)


@event.listens_for(DictionaryEntry, "before_update")
def _set_normalized_on_update(_mapper, _connection, target):  # type: ignore[no-untyped-def]
    _refresh_normalized(target)


class DictionaryExample(Base):
    __tablename__ = "dictionary_examples"

    id = Column(Integer, primary_key=True, index=True)
    entry_id = Column(Integer, ForeignKey("dictionary_entries.id", ondelete="CASCADE"), nullable=False)
    source_sentence = Column(Text, nullable=False)
    bassa_sentence = Column(Text, nullable=False)

    entry = relationship("DictionaryEntry", back_populates="examples")
