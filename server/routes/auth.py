from datetime import datetime, timedelta, timezone
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import jwt

from server.db import db  # adjust import to your actual db connection file

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

def require_user_id(authorization: str | None) -> int:
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

    conn = db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, name, role, password_hash
                FROM users
                WHERE lower(email) = %s
                LIMIT 1
                """,
                (email,),
            )
            row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user_id, db_email, name, role, password_hash = row

        if not password_hash or not pwd_context.verify(req.password, password_hash):
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
    finally:
        conn.close()


@router.get("/me")
def me(authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)

    sql_user = """
    SELECT id, name, email, COALESCE(role,'student') as role
    FROM users
    WHERE id = %s
    LIMIT 1;
    """

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_user, [user_id])
            u = cur.fetchone()

            if not u:
                raise HTTPException(status_code=401, detail="User not found")

            role = u[3] or "student"
            student_id = None
            company_id = None

            if role == "student":
                cur.execute("SELECT id FROM students WHERE user_id = %s LIMIT 1;", [user_id])
                s = cur.fetchone()
                student_id = s[0] if s else None

            if role == "admin":
                # adjust this query to match YOUR companies/admin mapping
                cur.execute("SELECT id FROM companies WHERE admin_user_id = %s LIMIT 1;", [user_id])
                c = cur.fetchone()
                company_id = c[0] if c else None

    return {
        "userId": u[0],
        "name": u[1],
        "email": u[2],
        "role": role,
        "studentId": student_id,
        "companyId": company_id,
    }
