from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, func

from backend.database import Base


class CorpusPair(Base):
    __tablename__ = "corpus_pairs"

    id = Column(Integer, primary_key=True, index=True)
    source_language = Column(String(2), nullable=False, index=True)
    source_text = Column(Text, nullable=False)
    bassa_text = Column(Text, nullable=False)
    domain = Column(String(100), nullable=True)
    source_reference = Column(String(255), nullable=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
