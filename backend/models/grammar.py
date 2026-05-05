from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, func

from backend.database import Base


class GrammaticalRule(Base):
    __tablename__ = "grammatical_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_name = Column(String(255), nullable=False)
    source_language = Column(String(2), nullable=False)
    pattern = Column(Text, nullable=False)
    transformation = Column(Text, nullable=False)
    priority = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
