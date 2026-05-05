import enum
from sqlalchemy import Column, Integer, String, Enum, Text, ForeignKey, DateTime, func

from backend.database import Base


class ContributionType(str, enum.Enum):
    dictionary = "dictionary"
    corpus = "corpus"


class ContributionStatus(str, enum.Enum):
    submitted = "submitted"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"


class Contribution(Base):
    __tablename__ = "contributions"

    id = Column(Integer, primary_key=True, index=True)
    contributor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(Enum(ContributionType), nullable=False)
    status = Column(Enum(ContributionStatus), default=ContributionStatus.submitted, nullable=False)
    source_language = Column(String(2), nullable=False)
    source_text = Column(Text, nullable=False)
    bassa_text = Column(Text, nullable=False)
    category = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewer_comment = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    reviewed_at = Column(DateTime, nullable=True)
