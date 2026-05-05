import enum
from sqlalchemy import Column, Integer, String, Enum, DateTime, func

from backend.database import Base


class UserRole(str, enum.Enum):
    contributor = "contributor"
    reviewer = "reviewer"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(191), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True)
    google_id = Column(String(128), unique=True, nullable=True, index=True)
    role = Column(Enum(UserRole), default=UserRole.contributor, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
