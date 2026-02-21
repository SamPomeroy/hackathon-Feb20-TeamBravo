"""
Auth Service — registration, login, token verification.
Bugs fixed:
  - MD5 → bcrypt
  - Hardcoded SECRET_KEY → env var (crashes if missing)
"""

import os
import sqlite3
import time
import uuid

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from database import get_conn, init_db
from models import UserRegister, UserLogin, TokenPayload

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required")

TOKEN_EXPIRY_SECONDS = int(os.getenv("TOKEN_EXPIRY_SECONDS", "86400"))

app = FastAPI(title="Auth Service", version="1.0.0")


@app.on_event("startup")
async def startup():
    init_db()


# --------------- Helpers ---------------

def hash_password(password: str) -> str:
    """Hash password with bcrypt (replaces MD5)."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: str, username: str, role: str = "fellow") -> str:
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": time.time() + TOKEN_EXPIRY_SECONDS,
        "iat": time.time(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


# --------------- Endpoints ---------------

@app.post("/register")
async def register(user: UserRegister):
    if len(user.username) < 3:
        raise HTTPException(status_code=400, detail="Username too short")
    if len(user.password) < 4:
        raise HTTPException(status_code=400, detail="Password too short (min 4 chars)")

    user_id = str(uuid.uuid4())
    password_hash = hash_password(user.password)

    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (id, username, email, password_hash) VALUES (?, ?, ?, ?)",
            (user_id, user.username, user.email, password_hash),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")
    conn.close()

    token = create_token(user_id, user.username)
    return {
        "message": "User registered successfully",
        "user_id": user_id,
        "username": user.username,
        "token": token,
    }


@app.post("/login")
async def login(user: UserLogin):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id, username, role, password_hash FROM users WHERE username = ? AND is_active = 1",
        (user.username,),
    )
    row = c.fetchone()
    conn.close()

    if not row or not check_password(user.password, row[3]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_id, username, role = row[0], row[1], row[2]
    token = create_token(user_id, username, role)
    return {
        "message": "Login successful",
        "token": token,
        "user_id": user_id,
        "username": username,
    }


@app.post("/verify")
async def verify_token(payload: TokenPayload):
    """Called by the gateway to verify tokens."""
    try:
        token = payload.token
        if token.startswith("Bearer "):
            token = token[7:]
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if decoded.get("exp", 0) < time.time():
            raise HTTPException(status_code=401, detail="Token expired")
        return {
            "valid": True,
            "user_id": decoded.get("user_id"),
            "username": decoded.get("username"),
            "role": decoded.get("role"),
        }
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/users/{user_id}")
async def get_user(user_id: str):
    """Get user profile info (called by gateway for /me)."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, email, created_at, role FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user_id": row[0],
        "username": row[1],
        "email": row[2],
        "created_at": row[3],
        "role": row[4],
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth"}


if __name__ == "__main__":
    import uvicorn
    print("Auth Service starting on port 8001")
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
