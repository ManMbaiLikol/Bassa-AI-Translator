from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserRegister(BaseModel):
    username: str
    email: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class GoogleToken(BaseModel):
    token: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str

    model_config = {"from_attributes": True}


class UserOutAdmin(BaseModel):
    id: int
    username: str
    email: str
    role: str
    google_id: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
