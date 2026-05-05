import re
import random
import string

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models.user import User
from backend.schemas.auth import UserRegister, UserLogin, Token, UserOut, GoogleToken
from backend.services.auth_service import (
    hash_password, verify_password, create_access_token, get_current_user,
)
from backend.rate_limit import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _unique_username(db: Session, name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]", "", name.replace(" ", "_"))[:20] or "user"
    candidate = base
    while db.query(User).filter(User.username == candidate).first():
        candidate = base + "".join(random.choices(string.digits, k=4))
    return candidate


@router.get("/config")
def auth_config():
    return {"google_client_id": settings.GOOGLE_CLIENT_ID or None}


@router.post("/register", response_model=UserOut, status_code=201)
@limiter.limit("5/minute")
def register(request: Request, data: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter((User.username == data.username) | (User.email == data.email)).first():
        raise HTTPException(status_code=400, detail="Username or email already taken")
    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": str(user.id), "role": user.role.value})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/google", response_model=Token)
@limiter.limit("10/minute")
def google_login(request: Request, data: GoogleToken, db: Session = Depends(get_db)):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google Sign-In not configured")

    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        idinfo = google_id_token.verify_oauth2_token(
            data.token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"Token Google invalide : {exc}")

    google_id = idinfo["sub"]
    email = idinfo.get("email", "")
    display_name = idinfo.get("name", "") or email.split("@")[0]

    # Cherche par google_id puis par email
    user = db.query(User).filter(
        (User.google_id == google_id) | (User.email == email)
    ).first()

    if user:
        if not user.google_id:
            user.google_id = google_id
            db.commit()
    else:
        username = _unique_username(db, display_name)
        user = User(
            username=username,
            email=email,
            hashed_password=None,
            google_id=google_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": str(user.id), "role": user.role.value})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
