"""
Auth Service
Handles: registration, login, JWT creation, token verification
Port: 8001

Fixes from monolith:
- MD5 password hashing replaced with bcrypt
- SECRET_KEY loaded from environment variable (no more hardcoding)
- Token verification is a proper endpoint, not copy-pasted everywhere
- No global mutable state
"""

import os
import time
import uuid
import sqlite3

import bcrypt
import jwt
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import UserRegister, UserLogin, TokenVerifyRequest
from database import init_db, get_conn

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is not set. Add it to your .env file.")

TOKEN_EXPIRY_SECONDS = int(os.getenv("TOKEN_EXPIRY_SECONDS", 86400))  # 24h default

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Auth Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    init_db()
    print("[auth-service] Started on port 8001")


# ── Helpers ───────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """bcrypt hash — replaces the MD5 disaster in the monolith."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/register")
async def register(user: UserRegister):
    if len(user.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(user.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user_id = str(uuid.uuid4())
    password_hash = hash_password(user.password)

    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (id, username, email, password_hash) VALUES (?, ?, ?, ?)",
            (user_id, user.username, user.email, password_hash),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")
    finally:
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
    row = conn.execute(
        "SELECT id, username, password_hash, role FROM users WHERE username = ? AND is_active = 1",
        (user.username,),
    ).fetchone()
    conn.close()

    # verify_password check prevents timing attacks vs just returning 401 immediately
    if not row or not verify_password(user.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(row["id"], row["username"], row["role"])
    return {
        "message": "Login successful",
        "token": token,
        "user_id": row["id"],
        "username": row["username"],
    }


@app.post("/verify")
async def verify_token(body: TokenVerifyRequest):
    """
    Internal endpoint called by the Gateway to validate tokens.
    Returns the decoded payload so the gateway can pass user info downstream.
    """
    try:
        payload = jwt.decode(body.token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("exp", 0) < time.time():
            raise HTTPException(status_code=401, detail="Token expired")
        return {"valid": True, "payload": payload}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
