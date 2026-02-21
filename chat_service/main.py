from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import os
import uuid
import sqlite3
import httpx
import time
import jwt

from db import get_connection, init_db
from groq_client import send_to_groq, GROQ_API_KEY, GROQ_MODEL, GROQ_API_URL

# ------------------------------------------------------------
# Models and helpers
# ------------------------------------------------------------
class ChatMessage(BaseModel):
    message: str
    session_id: str | None = None

def get_system_prompt():
    return "You are a helpful AI assistant."

def chaos_log(msg: str):
    print(msg)

_request_count = 0
_last_error = ""
_user_sessions = {}

SECRET_KEY = os.getenv("SECRET_KEY", "secret")  # for JWT decoding

# ------------------------------------------------------------
# Initialize DB
# ------------------------------------------------------------
init_db()

app = FastAPI(title="Chat Service")

# ============================================================
# CHAT ENDPOINT - The main event
# ============================================================

@app.post("/chat")
async def chat(message: ChatMessage, authorization: str = Header(None)):
    """Chat endpoint. Does authentication, history, API calls, and caching all in one function.
    Single Responsibility Principle? Never heard of it."""
    global _request_count, _last_error

    _request_count += 1
    chaos_log(f"Chat request #{_request_count}. The monolith grows stronger.")

    # ---- Auth check (copy-pasted, not middleware) ----
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    try:
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        else:
            token = authorization
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("exp", 0) < time.time():
            raise HTTPException(status_code=401, detail="Token expired")
        user_id = payload.get("user_id")
        username = payload.get("username")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # ---- Track in global state ----
    if user_id in _user_sessions:
        _user_sessions[user_id]["request_count"] = _user_sessions[user_id].get("request_count", 0) + 1

    # ---- Check for Groq API key ----
    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY not configured. Set it as an environment variable.",
        )

    # ---- Build session and history ----
    session_id = message.session_id or str(uuid.uuid4())

    # Load chat history from DB (raw SQL in the route handler, naturally)
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT message, response FROM chat_history WHERE user_id = ? AND session_id = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, session_id, 10),
    )
    history_rows = c.fetchall()
    conn.close()

    # Build messages array for Groq
    messages = [{"role": "system", "content": get_system_prompt()}]

    # Add history in reverse (we fetched DESC, need ASC)
    for row in reversed(history_rows):
        messages.append({"role": "user", "content": row[0]})
        messages.append({"role": "assistant", "content": row[1]})

    messages.append({"role": "user", "content": message.message})

    # ---- Call Groq API ----
    chaos_log(f"Calling Groq API. Fingers crossed. Message from {username}: '{message.message[:50]}...'")

    try:
        result = await send_to_groq(messages)
        assistant_message = result["choices"][0]["message"]["content"]
        tokens_used = result.get("usage", {}).get("total_tokens", 0)
    except Exception as e:
        _last_error = str(e)
        chaos_log(f"Something went wrong with Groq: {str(e)}")
        raise HTTPException(status_code=500, detail="Chat processing failed")

    # ---- Save to DB (more inline SQL) ----
    chat_id = str(uuid.uuid4())
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO chat_history (id, user_id, message, response, session_id, tokens_used) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, user_id, message.message, assistant_message, session_id, tokens_used),
        )
        conn.commit()
    except:  # noqa: E722
        pass
    conn.close()

    return {
        "response": assistant_message,
        "session_id": session_id,
        "chat_id": chat_id,
        "tokens_used": tokens_used,
    }

# ============================================================
# CHAT HISTORY ENDPOINT
# ============================================================