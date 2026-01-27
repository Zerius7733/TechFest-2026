from datetime import datetime, timedelta, timezone
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import jwt

# from server.db import db  # DB disabled
from server.csv_store import load_csv, safe_int

router = APIRouter(prefix="/api/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET = os.getenv("JWT_SECRET", "dev_only_change_me")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_EXPIRES_MIN = 60 * 24  # 24h
from fastapi import Header
from jose import JWTError


class LoginRequest(BaseModel):
    email: str
    password: str

def require_user_id(authorization: str | None = Header(default=None)) -> int:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    token = parts[1].strip()

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    try:
        return int(sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid user id")


def create_access_token(payload: dict) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=JWT_EXPIRES_MIN)
    to_encode = {**payload, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)


@router.post("/login")
def login(req: LoginRequest):
    email = req.email.strip().lower()

    # DB disabled. Previous query:
    # SELECT id, email, name, role, password_hash FROM users WHERE lower(email) = %s LIMIT 1;
    users = load_csv("users")
    row = None
    for u in users:
        if (u.get("email") or "").strip().lower() == email:
            row = u
            break

    if not row:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_id = safe_int(row.get("id"))
    db_email = row.get("email") or ""
    name = row.get("name") or ""
    role = row.get("role") or "student"
    password_hash = row.get("password_hash") or ""

    if not password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    ok = False
    try:
        ok = pwd_context.verify(req.password, password_hash)
    except Exception:
        # fallback: allow plaintext match for dev DB rows
        ok = (req.password == password_hash)

    if not ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": str(user_id), "role": role})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "email": db_email,
            "name": name,
            "role": role,
        },
    }


@router.get("/me")
def me(authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)

    # DB disabled. Previous query:
    # SELECT id, name, email, COALESCE(role,'student') as role FROM users WHERE id = %s LIMIT 1;
    users = load_csv("users")
    profiles = load_csv("student_profiles")
    company_profiles = load_csv("company_profiles")

    u = None
    for user in users:
        if safe_int(user.get("id")) == safe_int(user_id):
            u = user
            break

    if not u:
        raise HTTPException(status_code=401, detail="User not found")

    role = u.get("role") or "student"
    student_id = None
    company_id = None

    if role == "student":
        for p in profiles:
            if safe_int(p.get("user_id")) == safe_int(user_id):
                student_id = safe_int(user_id)
                break

    if role == "admin":
        for cp in company_profiles:
            if safe_int(cp.get("user_id")) == safe_int(user_id):
                company_id = safe_int(cp.get("company_id"))
                break

    return {
        "userId": safe_int(u.get("id")),
        "name": u.get("name"),
        "email": u.get("email"),
        "role": role,
        "studentId": student_id,
        "companyId": company_id,
    }
