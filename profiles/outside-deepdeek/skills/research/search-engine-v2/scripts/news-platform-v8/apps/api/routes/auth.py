"""routes/auth.py — Login/Register/Auth. bcrypt password hashing."""

import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from passlib.hash import bcrypt
from apps.api.database import get_db
from apps.api.models import User, Subscription
from apps.api.schemas import LoginIn, TokenOut, SubscribeIn

router = APIRouter(tags=["auth"])

SECRET_KEY = os.environ.get("JWT_SECRET")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET environment variable is required")

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    # Compatible with old SHA256 format (salt:hash) — auto-upgrade on login
    if ":" in hashed and not hashed.startswith("$2"):
        salt, h = hashed.split(":", 1)
        import hashlib
        return hashlib.sha256((salt + password).encode()).hexdigest() == h
    try:
        return bcrypt.verify(password, hashed)
    except ValueError:
        return False


def create_token(user_id: int, level: str) -> str:
    return jwt.encode(
        {"user_id": user_id, "level": level, "exp": datetime.utcnow() + timedelta(days=7)},
        SECRET_KEY, algorithm=ALGORITHM,
    )


def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM])
        user = db.query(User).filter(User.id == payload["user_id"]).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_admin(user: User = Depends(get_current_user)) -> User:
    if user.level != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def get_vip(user: User = Depends(get_current_user)) -> User:
    if user.level not in ("vip", "admin"):
        raise HTTPException(status_code=403, detail="VIP only")
    return user


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": create_token(user.id, user.level), "level": user.level}


@router.post("/auth/register")
def register(body: LoginIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email exists")
    user = User(email=body.email, password_hash=hash_password(body.password), level="free")
    db.add(user)
    db.commit()
    return {"ok": True}


@router.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "level": user.level}
