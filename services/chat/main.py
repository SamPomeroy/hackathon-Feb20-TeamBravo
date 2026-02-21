"""
Chat Service — Groq API integration and conversation history.
Fixes from monolith:
  - No global mutable state for sessions
  - Clean error handling (no bare except: pass)
  - Auth delegated to gateway
"""

import os
import sqlite3
import uuid

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from typing import Optional

from database import get_conn, init_db
from models import ChatMessage

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_CHAT_HISTORY = int(os.getenv("MAX_CHAT_HISTORY", "10"))

# Content DB path — used read-only to build system prompt context
CONTENT_DB_PATH = os.getenv("CONTENT_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "content", "content.db"))

app = FastAPI(title="Chat Service", version="1.0.0")


@app.on_event("startup")
async def startup():
    init_db()


# --------------- Helpers ---------------

def get_content_context():
    """Load content from Content DB for system prompt context."""
    try:
        conn = sqlite3.connect(CONTENT_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT title, body FROM content ORDER BY created_at DESC LIMIT 5")
        rows = c.fetchall()
        conn.close()
        if rows:
            context = "\n\nHere is some reference content from the AISE program:\n"
            for title, body in rows:
                context += f"\n--- {title} ---\n{body}\n"
            return context
    except Exception:
        pass
    return ""


def get_system_prompt():
    base_prompt = """You are AISE ASK, a helpful AI assistant for the AI Safety and Engineering (AISE) fellowship program.
You help fellows with questions about:
- The AISE curriculum and schedule
- AI safety concepts (alignment, interpretability, robustness)
- Prompt engineering techniques
- Building AI agents
- Technical concepts covered in the program
- Program logistics and schedules

Be friendly, concise, and helpful. If you don't know something specific about the AISE program,
say so honestly rather than making things up. You can still help with general AI/ML questions.

Keep responses focused and practical. Fellows are busy learning - respect their time."""
    return base_prompt + get_content_context()


# --------------- Endpoints ---------------

@app.post("/chat")
async def chat(message: ChatMessage, x_user_id: str = Header(None), x_username: str = Header(None)):
    """Gateway forwards user info via X-User-Id / X-Username headers after verifying auth."""
    user_id = x_user_id
    username = x_username or "unknown"

    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user context")

    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured")

    session_id = message.session_id or str(uuid.uuid4())

    # Load history
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT message, response FROM chat_history WHERE user_id = ? AND session_id = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, session_id, MAX_CHAT_HISTORY),
    )
    history_rows = c.fetchall()
    conn.close()

    messages = [{"role": "system", "content": get_system_prompt()}]
    for row in reversed(history_rows):
        messages.append({"role": "user", "content": row[0]})
        messages.append({"role": "assistant", "content": row[1]})
    messages.append({"role": "user", "content": message.message})

    # Call Groq
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 1024,
                },
            )
            if response.status_code != 200:
                raise HTTPException(status_code=502, detail=f"LLM API error: {response.status_code}")
            result = response.json()
            assistant_message = result["choices"][0]["message"]["content"]
            tokens_used = result.get("usage", {}).get("total_tokens", 0)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="LLM API timeout")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")

    # Save to DB
    chat_id = str(uuid.uuid4())
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO chat_history (id, user_id, message, response, session_id, tokens_used) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, user_id, message.message, assistant_message, session_id, tokens_used),
        )
        conn.commit()
    except Exception as e:
        print(f"Warning: could not save chat history: {e}")
    conn.close()

    return {
        "response": assistant_message,
        "session_id": session_id,
        "chat_id": chat_id,
        "tokens_used": tokens_used,
    }


@app.get("/chat/history")
async def get_chat_history(
    session_id: Optional[str] = None,
    limit: int = 20,
    x_user_id: str = Header(None),
):
    user_id = x_user_id
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user context")

    conn = get_conn()
    c = conn.cursor()
    if session_id:
        c.execute(
            "SELECT id, message, response, timestamp, session_id, tokens_used FROM chat_history WHERE user_id = ? AND session_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, session_id, limit),
        )
    else:
        c.execute(
            "SELECT id, message, response, timestamp, session_id, tokens_used FROM chat_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit),
        )
    rows = c.fetchall()
    conn.close()

    history = [
        {"id": r[0], "message": r[1], "response": r[2], "timestamp": r[3], "session_id": r[4], "tokens_used": r[5]}
        for r in rows
    ]
    return {"history": history, "count": len(history)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "chat"}


if __name__ == "__main__":
    import uvicorn
    print("Chat Service starting on port 8002")
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
