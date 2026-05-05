from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, func

from backend.database import Base


class TranslationHistory(Base):
    __tablename__ = "translation_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_language = Column(String(2), nullable=False, index=True)
    source_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=False)
    engine = Column(String(50), nullable=False, index=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
