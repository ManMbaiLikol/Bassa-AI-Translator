from sqlalchemy import Column, Integer, String, Boolean, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship

from backend.database import Base


class DictionaryEntry(Base):
    __tablename__ = "dictionary_entries"

    id = Column(Integer, primary_key=True, index=True)
    source_language = Column(String(2), nullable=False, index=True)  # fr or en
    source_word = Column(String(191), nullable=False, index=True)
    bassa_word = Column(String(255), nullable=False)
    phonetic = Column(String(255), nullable=True)
    category = Column(String(50), nullable=True)  # noun, verb, adjective, etc.
    gender = Column(String(20), nullable=True)
    plural_form = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    examples = relationship("DictionaryExample", back_populates="entry", cascade="all, delete-orphan")


class DictionaryExample(Base):
    __tablename__ = "dictionary_examples"

    id = Column(Integer, primary_key=True, index=True)
    entry_id = Column(Integer, ForeignKey("dictionary_entries.id", ondelete="CASCADE"), nullable=False)
    source_sentence = Column(Text, nullable=False)
    bassa_sentence = Column(Text, nullable=False)

    entry = relationship("DictionaryEntry", back_populates="examples")
