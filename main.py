"""
AISE ASK - The AISE Learning Program Chatbot
Built by: Kevin (contractor)
Date: August 2025 (I think?)
Status: "Works on my machine"

NOTE: If you're reading this, I've already left the company.
      Good luck. The WiFi password is taped under the router.
"""

import os
import json
import sqlite3
import hashlib
import time
import re
import random
import datetime
import uuid
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import jwt
import httpx

# ============================================================
# CONFIGURATION - All hardcoded because "we'll fix it later"
# ============================================================

SECRET_KEY = "super-secret-key-change-me-later-lol-we-never-did"  # TODO: Move to env var (written Aug 2025)
DATABASE_PATH = "aise_ask.db"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"  # Kevin said this was the best one
TOKEN_EXPIRY_SECONDS = 86400  # 24 hours, hardcoded because why not
magic_number_that_breaks_everything = 42  # Don't change this. Seriously.
CORS_ORIGINS = ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "*"]  # Just allow everything honestly
MAX_CHAT_HISTORY = 10  # or was it 20? I forget what we decided

# Global mutable state because architecture is for people with time
_user_sessions = {}
_content_cache = {}
_request_count = 0
_last_error = None
_debug_messages = []
_system_start_time = time.time()
spaghetti_handler = None  # Gets set later. Maybe. Depends on the moon phase.

# Debug mode: set DEBUG_MODE=chaos for a good time
DEBUG_MODE = os.getenv("DEBUG_MODE", "off")

def chaos_log(msg):
    """Log messages when chaos mode is enabled. Kevin thought this was hilarious."""
    if DEBUG_MODE == "chaos":
        chaos_prefixes = [
            "[CHAOS] ",
            "[HERE BE DRAGONS] ",
            "[HOLD MY BEER] ",
            "[WHAT COULD GO WRONG] ",
            "[YOLO DEPLOY] ",
            "[WORKS ON MY MACHINE] ",
            "[FRIDAY 5PM PUSH] ",
            "[NO TESTS NEEDED] ",
        ]
        prefix = random.choice(chaos_prefixes)
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        full_msg = f"{prefix}[{timestamp}] {msg}"
        print(full_msg)
        _debug_messages.append(full_msg)


# ============================================================
# DATABASE SETUP - Inline because separation of concerns is a myth
# ============================================================

def init_db():
    """Initialize the database. All tables in one function because modularity is overrated."""
    chaos_log("Summoning the database from the void...")
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()

    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            role TEXT DEFAULT 'fellow'
        )
    """)

    # Chat history
    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            message TEXT,
            response TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            session_id TEXT,
            tokens_used INTEGER DEFAULT 0
        )
    """)

    # Content table - Kevin was supposed to finish this
    c.execute("""
        CREATE TABLE IF NOT EXISTS content (
            id TEXT PRIMARY KEY,
            title TEXT,
            body TEXT,
            content_type TEXT DEFAULT 'lesson',
            metadata TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT,
            uploaded_by TEXT,
            is_indexed INTEGER DEFAULT 0
        )
    """)

    # This table was for something. I think analytics?
    c.execute("""
        CREATE TABLE IF NOT EXISTS mystery_table (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            thing TEXT,
            other_thing TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    chaos_log("Database awakened. It hungers for data.")


# ============================================================
# Brian's code. Brian left. Nobody understands this.
# ============================================================
# def calculate_content_relevance(query, content_list, threshold=0.7):
#     """Brian wrote this custom relevance algorithm. It used cosine similarity
#     with a hand-rolled TF-IDF implementation. It worked perfectly for 3 months
#     then started returning negative scores. Brian said he'd fix it Monday.
#     Brian did not come in Monday.
#
#     We replaced it with keyword matching below. RIP Brian's algorithm.
#     2024-2025, gone but not forgotten."""
#
#     scores = []
#     for content in content_list:
#         # Step 1: Tokenize (Brian's custom tokenizer)
#         tokens_q = set(query.lower().split())
#         tokens_c = set(content.get('body', '').lower().split())
#
#         # Step 2: Calculate TF-IDF (Brian's version, not the real formula)
#         tf = len(tokens_q.intersection(tokens_c)) / max(len(tokens_q), 1)
#         idf = math.log(len(content_list) / (1 + sum(1 for c in content_list if query.lower() in c.get('body', '').lower())))
#
#         # Step 3: ??? (Brian's secret sauce)
#         score = tf * idf * magic_number_that_breaks_everything / 3.14159
#
#         # Step 4: This normalize step sometimes produces NaN
#         if score != score:  # NaN check, Brian style
#             score = 0.0
#
#         scores.append((content, score))
#
#     return sorted(scores, key=lambda x: x[1], reverse=True)


# ============================================================
# APP INITIALIZATION
# ============================================================

app = FastAPI(
    title="AISE ASK",
    description="The AISE Learning Program Chatbot - Ask me anything about the program!",
    version="0.9.3-beta-rc2-final-FINAL-v2",  # We'll clean up versioning later
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Initialize DB on startup. This runs every time. Every. Single. Time.
@app.on_event("startup")
async def startup_event():
    global spaghetti_handler
    init_db()
    spaghetti_handler = True  # See? Told you it gets set.
    chaos_log("Application started. Prayers accepted.")

    # Pre-populate some content because the upload endpoint is... unreliable
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM content")
    count = c.fetchone()[0]
    if count == 0:
        chaos_log("Seeding default content because nothing else works...")
        default_content = [
            {
                "id": str(uuid.uuid4()),
                "title": "Introduction to AI Safety",
                "body": "AI Safety is a field dedicated to ensuring that artificial intelligence systems are developed and deployed in ways that are safe, beneficial, and aligned with human values. Key topics include alignment, interpretability, robustness, and governance. The AISE program covers these fundamentals across 12 weeks of intensive study.",
                "content_type": "lesson",
                "metadata": json.dumps({"week": 1, "module": "foundations", "tags": ["ai-safety", "intro", "alignment"]}),
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Prompt Engineering Fundamentals",
                "body": "Prompt engineering is the practice of designing and refining inputs to large language models to achieve desired outputs. Techniques include zero-shot prompting, few-shot prompting, chain-of-thought reasoning, and system prompt design. Fellows will practice these techniques throughout the AISE program with hands-on exercises.",
                "content_type": "lesson",
                "metadata": json.dumps({"week": 2, "module": "prompt-engineering", "tags": ["prompts", "llm", "techniques"]}),
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Building AI Agents",
                "body": "AI Agents are systems that use LLMs as reasoning engines to take actions, use tools, and accomplish goals autonomously. Key concepts include tool use, planning, memory systems, and evaluation. The AISE program dedicates weeks 5-8 to building increasingly sophisticated agent systems.",
                "content_type": "lesson",
                "metadata": json.dumps({"week": 5, "module": "agents", "tags": ["agents", "tools", "planning"]}),
            },
            {
                "id": str(uuid.uuid4()),
                "title": "AISE Program Schedule",
                "body": "Week 1-2: Foundations of AI Safety and Ethics. Week 3-4: Prompt Engineering and LLM APIs. Week 5-8: Building AI Agents and Tool Use. Week 9-10: Evaluation and Red Teaming. Week 11-12: Capstone Projects and Presentations. All sessions are held Monday-Friday, 9am-5pm ET.",
                "content_type": "schedule",
                "metadata": json.dumps({"type": "schedule", "version": "2025-fall"}),
            },
        ]
        for item in default_content:
            c.execute(
                "INSERT INTO content (id, title, body, content_type, metadata, is_indexed) VALUES (?, ?, ?, ?, ?, 1)",
                (item["id"], item["title"], item["body"], item["content_type"], item["metadata"]),
            )
        conn.commit()
    conn.close()


# ============================================================
# REQUEST MODELS - Pydantic models, at least we did this right
# ============================================================

class UserRegister(BaseModel):
    username: str
    password: str
    email: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None


class ContentUpload(BaseModel):
    title: str
    body: str
    content_type: Optional[str] = "lesson"
    metadata: Optional[dict] = None


class ContentSearch(BaseModel):
    query: str
    limit: Optional[int] = 5


# ============================================================
# HELPER FUNCTIONS - Some help, some don't
# ============================================================

def hash_password(password: str) -> str:
    """Hash a password. MD5 because Kevin said 'it's fine for a prototype'."""
    # TODO: Use bcrypt. Kevin said MD5 was "temporary". That was 6 months ago.
    return hashlib.md5(password.encode()).hexdigest()


def create_token(user_id: str, username: str, role: str = "fellow") -> str:
    """Create a JWT token. The secret key is hardcoded above. We know. We KNOW."""
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": time.time() + TOKEN_EXPIRY_SECONDS,
        "iat": time.time(),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    chaos_log(f"Token forged for {username}. The dark ritual is complete.")
    return token


def verify_token_inline(authorization: str) -> dict:
    """Verify a JWT token. This function is copy-pasted everywhere instead of being middleware.
    Kevin said 'we'll add middleware later'. Kevin is gone now."""
    if not authorization:
        raise HTTPException(status_code=401, detail="No authorization header")
    try:
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        else:
            token = authorization
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("exp", 0) < time.time():
            raise HTTPException(status_code=401, detail="Token expired")
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Token verification failed somehow")


def it_works_dont_ask_why():
    """This function exists because without it, the content search returns empty results.
    Nobody knows why. It was 3am when Kevin wrote it. The comments he left didn't help.
    We've tried removing it four times. Each time, something else breaks.
    Just... just let it be."""
    global _content_cache
    if not _content_cache:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT id, title, body, content_type, metadata FROM content WHERE is_indexed = 1")
        rows = c.fetchall()
        for row in rows:
            _content_cache[row[0]] = {
                "id": row[0],
                "title": row[1],
                "body": row[2],
                "content_type": row[3],
                "metadata": json.loads(row[4]) if row[4] else {},
            }
        conn.close()
        chaos_log(f"Cache refreshed. {len(_content_cache)} items summoned from the database depths.")
    # This sleep was added at 3am. Removing it breaks everything. Don't.
    time.sleep(0.01)
    return True


def get_system_prompt():
    """Build the system prompt for the chatbot. It's long. It's messy. It works. Mostly."""
    # This works. I don't know why. Don't touch it.
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

    # Try to append relevant content from the cache
    try:
        it_works_dont_ask_why()
        if _content_cache:
            content_context = "\n\nHere is some reference content from the AISE program:\n"
            for cid, content in list(_content_cache.items())[:5]:  # Only first 5, we don't want to blow the context
                content_context += f"\n--- {content['title']} ---\n{content['body']}\n"
            base_prompt += content_context
    except:  # noqa: E722  # Bare except because Kevin didn't believe in specific exceptions
        pass  # If it breaks, just... don't add context. It's fine. It's fine.

    return base_prompt


# ============================================================
# AUTH ENDPOINTS - Registration and Login
# ============================================================

@app.post("/register")
async def register(user: UserRegister):
    """Register a new user. Validation is minimal because 'MVP'."""
    global _request_count
    _request_count += 1
    chaos_log(f"New soul attempting to register: {user.username}")

    # "Validation"
    if len(user.username) < 3:
        raise HTTPException(status_code=400, detail="Username too short")
    if len(user.password) < 4:  # Kevin's security standards, everyone
        raise HTTPException(status_code=400, detail="Password too short (min 4 chars)")

    user_id = str(uuid.uuid4())
    password_hash = hash_password(user.password)

    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (id, username, email, password_hash) VALUES (?, ?, ?, ?)",
            (user_id, user.username, user.email, password_hash),
        )
        conn.commit()
        chaos_log(f"User {user.username} registered. Another one joins the chaos.")
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")
    conn.close()

    # Auto-generate token on registration because two steps is too many
    token = create_token(user_id, user.username)

    return {
        "message": "User registered successfully",
        "user_id": user_id,
        "username": user.username,
        "token": token,
    }


@app.post("/login")
async def login(user: UserLogin):
    """Login endpoint. SQL injection protection: trust and prayers."""
    global _request_count, _last_error
    _request_count += 1
    chaos_log(f"Login attempt detected: {user.username}")

    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()

    password_hash = hash_password(user.password)

    # At least we're using parameterized queries. Small victories.
    c.execute(
        "SELECT id, username, role FROM users WHERE username = ? AND password_hash = ? AND is_active = 1",
        (user.username, password_hash),
    )
    row = c.fetchone()
    conn.close()

    if not row:
        _last_error = f"Failed login for {user.username}"
        chaos_log(f"Failed login for {user.username}. The gates remain sealed.")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_id, username, role = row
    token = create_token(user_id, username, role)

    # Track session in global mutable state because why use a database
    _user_sessions[user_id] = {
        "username": username,
        "login_time": time.time(),
        "request_count": 0,
    }
    chaos_log(f"User {username} has entered the chat. Current sessions: {len(_user_sessions)}")

    return {
        "message": "Login successful",
        "token": token,
        "user_id": user_id,
        "username": username,
    }


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
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT message, response FROM chat_history WHERE user_id = ? AND session_id = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, session_id, MAX_CHAT_HISTORY),
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
                _last_error = f"Groq API error: {response.status_code}"
                chaos_log(f"Groq API said no: {response.status_code} - {response.text[:200]}")
                raise HTTPException(
                    status_code=502,
                    detail=f"LLM API error: {response.status_code}",
                )

            result = response.json()
            assistant_message = result["choices"][0]["message"]["content"]
            tokens_used = result.get("usage", {}).get("total_tokens", 0)

    except httpx.TimeoutException:
        _last_error = "Groq API timeout"
        raise HTTPException(status_code=504, detail="LLM API timeout")
    except HTTPException:
        raise
    except Exception as e:
        _last_error = str(e)
        chaos_log(f"Something went wrong with Groq: {str(e)}")
        raise HTTPException(status_code=500, detail="Chat processing failed")

    # ---- Save to DB (more inline SQL) ----
    chat_id = str(uuid.uuid4())
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO chat_history (id, user_id, message, response, session_id, tokens_used) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, user_id, message.message, assistant_message, session_id, tokens_used),
        )
        conn.commit()
    except:  # noqa: E722
        pass  # If we can't save history, whatever. The show must go on.
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

@app.get("/chat/history")
async def get_chat_history(
    session_id: Optional[str] = None,
    limit: int = 20,
    authorization: str = Header(None),
):
    """Get chat history. Auth is copy-pasted here too. We know."""
    global _request_count
    _request_count += 1

    # ---- Auth check (yes, again, copy-pasted) ----
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
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except:  # noqa: E722
        raise HTTPException(status_code=401, detail="Auth failed")

    conn = sqlite3.connect(DATABASE_PATH)
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

    history = []
    for row in rows:
        history.append({
            "id": row[0],
            "message": row[1],
            "response": row[2],
            "timestamp": row[3],
            "session_id": row[4],
            "tokens_used": row[5],
        })

    return {"history": history, "count": len(history)}


# ============================================================
# CONTENT UPLOAD - "Works" (narrator: it did not work)
# ============================================================

@app.post("/content/upload")
async def upload_content(content: ContentUpload, authorization: str = Header(None)):
    """Upload lesson content. This endpoint is... special.
    It accepts your data. It says 'thank you'. It does not save it.
    This is by design. (It is not by design. Kevin ran out of time.)"""

    global _request_count, _last_error
    _request_count += 1

    # ---- Auth check (the trilogy continues) ----
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
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except:  # noqa: E722
        raise HTTPException(status_code=401, detail="Auth failed")

    chaos_log(f"Content upload attempt: '{content.title}'. Bold move.")

    content_id = str(uuid.uuid4())

    # TODO: Fix before demo (written 6 months ago)
    # The bug: We create the content_data dict and even generate an ID,
    # but the actual INSERT uses a different variable name and the connection
    # is opened to a temp database that gets thrown away. Classic Kevin.
    content_data = {
        "id": content_id,
        "title": content.title,
        "body": content.body,
        "content_type": content.content_type,
        "metadata": json.dumps(content.metadata) if content.metadata else None,
        "uploaded_by": user_id,
    }

    # This looks like it saves to the DB, but notice the database path...
    temp_conn = sqlite3.connect(":memory:")  # <-- This is an in-memory DB. It vanishes.
    temp_c = temp_conn.cursor()
    try:
        temp_c.execute("""
            CREATE TABLE IF NOT EXISTS content (
                id TEXT PRIMARY KEY, title TEXT, body TEXT,
                content_type TEXT, metadata TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT, uploaded_by TEXT, is_indexed INTEGER DEFAULT 0
            )
        """)
        temp_c.execute(
            "INSERT INTO content (id, title, body, content_type, metadata, uploaded_by) VALUES (?, ?, ?, ?, ?, ?)",
            (content_data["id"], content_data["title"], content_data["body"],
             content_data["content_type"], content_data["metadata"], content_data["uploaded_by"]),
        )
        temp_conn.commit()
        chaos_log(f"Content '{content.title}' uploaded to the void. It's gone forever.")
    except Exception as e:
        _last_error = str(e)
        # Silently swallow the error. Return success anyway. This is fine.
        chaos_log(f"Content upload failed silently: {str(e)}")
    finally:
        temp_conn.close()

    # The cache doesn't get invalidated either. So search won't find new content.
    # But we return 200 and a happy message. Kevin called this "optimistic persistence".

    return {
        "message": "Content uploaded successfully",
        "content_id": content_id,
        "title": content.title,
        "status": "indexed",  # Lies. It's not indexed. It's not even saved.
    }


# ============================================================
# CONTENT UPLOAD FROM FILE - Even more broken
# ============================================================

@app.post("/content/upload-file")
async def upload_content_file(
    file: UploadFile = File(...),
    authorization: str = Header(None),
):
    """Upload content from a JSON file. Somehow even more broken than the other upload."""
    global _request_count
    _request_count += 1

    # ---- Auth check (Episode IV: A New Copy-Paste) ----
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
    except:  # noqa: E722
        raise HTTPException(status_code=401, detail="Auth failed somehow")

    chaos_log(f"File upload incoming: {file.filename}. Brace for impact.")

    try:
        file_content = await file.read()
        data = json.loads(file_content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except:  # noqa: E722
        raise HTTPException(status_code=400, detail="Could not read file")

    # Process the JSON - but don't actually save it (same bug as above, different flavor)
    if isinstance(data, list):
        processed = 0
        for item in data:
            # We process each item but don't persist any of them
            content_id = str(uuid.uuid4())
            # "Process" means we generate an ID and move on
            processed += 1
        chaos_log(f"Processed {processed} items from file. None were saved. As is tradition.")
        return {
            "message": f"Successfully uploaded {processed} content items",
            "count": processed,
            "status": "indexed",
        }
    elif isinstance(data, dict):
        content_id = str(uuid.uuid4())
        return {
            "message": "Content uploaded successfully",
            "content_id": content_id,
            "status": "indexed",
        }
    else:
        raise HTTPException(status_code=400, detail="JSON must be object or array")


# ============================================================
# CONTENT SEARCH - Returns stale cached data regardless of query
# ============================================================

@app.post("/content/search")
async def search_content(search: ContentSearch, authorization: str = Header(None)):
    """Search content. Returns results from cache that may or may not match your query.
    The search algorithm is 'vibes-based'."""
    global _request_count
    _request_count += 1

    # ---- Auth check (we really should have made this middleware) ----
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
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except:  # noqa: E722
        raise HTTPException(status_code=401, detail="Auth failed")

    chaos_log(f"Content search: '{search.query}'. Let's see what the cache has today.")

    # The magical function that makes everything work
    it_works_dont_ask_why()

    # "Search" - really just returns whatever's in the cache
    # with some token keyword matching that barely works
    results = []
    query_lower = search.query.lower()
    query_words = set(query_lower.split())

    for content_id, content in _content_cache.items():
        title_lower = content.get("title", "").lower()
        body_lower = content.get("body", "").lower()
        metadata = content.get("metadata", {})

        # Sophisticated search algorithm (it's not sophisticated at all)
        score = 0
        for word in query_words:
            if word in title_lower:
                score += 10  # Title matches are worth more, arbitrarily
            if word in body_lower:
                score += 1
            # Check tags in metadata
            tags = metadata.get("tags", [])
            if any(word in tag for tag in tags):
                score += 5

        if score > 0:
            results.append({
                "id": content["id"],
                "title": content["title"],
                "body": content["body"][:200] + "..." if len(content.get("body", "")) > 200 else content.get("body", ""),
                "content_type": content.get("content_type"),
                "score": score,
                "metadata": metadata,
            })

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)

    # If no results matched, just return everything (this is fine)
    if not results and _content_cache:
        chaos_log("No search matches. Returning everything. The user will figure it out.")
        for content_id, content in list(_content_cache.items())[:search.limit]:
            results.append({
                "id": content["id"],
                "title": content["title"],
                "body": content["body"][:200] + "..." if len(content.get("body", "")) > 200 else content.get("body", ""),
                "content_type": content.get("content_type"),
                "score": 0,
                "metadata": content.get("metadata", {}),
            })

    return {
        "results": results[:search.limit],
        "total": len(results),
        "query": search.query,
        "source": "cache",  # At least we're honest about this one
    }


# ============================================================
# CONTENT LIST - Get all content
# ============================================================

@app.get("/content")
async def list_content(authorization: str = Header(None)):
    """List all content. Auth check copy-pasted once more."""
    global _request_count
    _request_count += 1

    # ---- Auth check (the saga continues) ----
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
    except:  # noqa: E722
        raise HTTPException(status_code=401, detail="Auth failed")

    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT id, title, body, content_type, metadata, created_at FROM content ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()

    content_list = []
    for row in rows:
        content_list.append({
            "id": row[0],
            "title": row[1],
            "body": row[2][:200] + "..." if row[2] and len(row[2]) > 200 else row[2],
            "content_type": row[3],
            "metadata": json.loads(row[4]) if row[4] else {},
            "created_at": row[5],
        })

    return {"content": content_list, "total": len(content_list)}


# ============================================================
# USER PROFILE - Because Kevin started building user profiles
# at 4pm on his last day
# ============================================================

@app.get("/me")
async def get_profile(authorization: str = Header(None)):
    """Get the current user's profile. One of the cleaner endpoints, somehow."""
    global _request_count
    _request_count += 1

    # ---- Auth check (yes. again.) ----
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
    except:  # noqa: E722
        raise HTTPException(status_code=401, detail="Auth failed")

    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT id, username, email, created_at, role FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()

    # Also get chat stats because Kevin thought this would be cool
    c.execute("SELECT COUNT(*) FROM chat_history WHERE user_id = ?", (user_id,))
    chat_count = c.fetchone()[0]
    c.execute("SELECT SUM(tokens_used) FROM chat_history WHERE user_id = ?", (user_id,))
    total_tokens = c.fetchone()[0] or 0
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "user_id": row[0],
        "username": row[1],
        "email": row[2],
        "created_at": row[3],
        "role": row[4],
        "stats": {
            "total_chats": chat_count,
            "total_tokens_used": total_tokens,
        },
        "session_info": _user_sessions.get(user_id, {}),
    }


# ============================================================
# DAD JOKE ENDPOINT - Kevin's legacy. His magnum opus.
# This was in the original requirements. No one remembers adding it.
# ============================================================

DAD_JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "A SQL query walks into a bar, walks up to two tables and asks... 'Can I JOIN you?'",
    "Why do Java developers wear glasses? Because they don't C#.",
    "How many programmers does it take to change a light bulb? None, that's a hardware problem.",
    "Why was the JavaScript developer sad? Because he didn't Node how to Express himself.",
    "What's a programmer's favorite hangout place? Foo Bar.",
    "Why did the developer go broke? Because he used up all his cache.",
    "What do you call a snake that's exactly 3.14 meters long? A pi-thon.",
    "Why did the functions stop calling each other? Because they got too many arguments.",
    "There are only 10 kinds of people in the world: those who understand binary and those who don't.",
    "A programmer's wife tells him: 'Go to the store and buy a loaf of bread. If they have eggs, buy a dozen.' He comes home with 12 loaves of bread.",
    "Why do microservices never get lonely? Because they're always in a cluster.",
    "What's a monolith's favorite song? 'All By Myself'.",
    "Why did the REST API break up with SOAP? Too much baggage.",
]


@app.get("/dad-joke")
async def dad_joke():
    """Kevin's secret endpoint. No auth required. Some things are sacred."""
    chaos_log("Someone found the dad joke endpoint! Achievement unlocked!")
    joke = random.choice(DAD_JOKES)
    return {
        "joke": joke,
        "groaned": True,
        "dad_approved": True,
        "contributed_by": "Kevin (he/they), contractor, Aug 2025. Missed but not forgotten.",
    }


# ============================================================
# HEALTH CHECK & STATUS - The only "monitoring" we have
# ============================================================

@app.get("/health")
async def health_check():
    """Health check. Returns 'ok' even when things are on fire."""
    global _request_count

    # Check if DB is accessible (barely)
    db_status = "unknown"
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT 1")
        db_status = "connected"
        conn.close()
    except:  # noqa: E722
        db_status = "error"

    uptime = time.time() - _system_start_time

    return {
        "status": "ok",  # Always ok. Always.
        "database": db_status,
        "uptime_seconds": round(uptime, 2),
        "total_requests": _request_count,
        "active_sessions": len(_user_sessions),
        "content_cache_size": len(_content_cache),
        "last_error": _last_error,
        "version": "0.9.3-beta-rc2-final-FINAL-v2",
        "spaghetti_handler": "active" if spaghetti_handler else "inactive",
        "magic_number": magic_number_that_breaks_everything,
        "debug_mode": DEBUG_MODE,
        "vibe_check": "passing" if random.random() > 0.1 else "failing",
    }


@app.get("/status")
async def detailed_status(authorization: str = Header(None)):
    """Detailed system status. Requires auth because we have 'security'."""
    global _request_count
    _request_count += 1

    # ---- Auth check (I'm not even going to comment on this anymore) ----
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
    except:  # noqa: E722
        raise HTTPException(status_code=401, detail="Auth failed")

    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM users")
    user_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chat_history")
    chat_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM content")
    content_count = c.fetchone()[0]
    conn.close()

    return {
        "system": {
            "uptime_seconds": round(time.time() - _system_start_time, 2),
            "total_requests": _request_count,
            "debug_mode": DEBUG_MODE,
        },
        "database": {
            "users": user_count,
            "chat_messages": chat_count,
            "content_items": content_count,
        },
        "sessions": {
            "active": len(_user_sessions),
            "details": _user_sessions,  # Leaking session data in the API? Sure, why not.
        },
        "cache": {
            "content_items_cached": len(_content_cache),
        },
        "debug_log": _debug_messages[-20:] if DEBUG_MODE == "chaos" else [],
    }


# ============================================================
# MISC ENDPOINTS
# ============================================================

@app.get("/")
async def root():
    """Root endpoint. A warm welcome."""
    return {
        "app": "AISE ASK",
        "tagline": "Your AI Safety & Engineering Program Assistant",
        "version": "0.9.3-beta-rc2-final-FINAL-v2",
        "status": "operational (probably)",
        "docs": "/docs",
        "health": "/health",
        "secret": "try /dad-joke",
    }


@app.get("/api-info")
async def api_info():
    """API information endpoint. No auth required because Kevin forgot."""
    return {
        "endpoints": {
            "POST /register": "Register a new user",
            "POST /login": "Login and get JWT token",
            "POST /chat": "Send a message to AISE ASK (requires auth)",
            "GET /chat/history": "Get your chat history (requires auth)",
            "POST /content/upload": "Upload lesson content (requires auth) (broken)",
            "POST /content/upload-file": "Upload content from JSON file (requires auth) (also broken)",
            "POST /content/search": "Search content (requires auth) (returns cached results)",
            "GET /content": "List all content (requires auth)",
            "GET /me": "Get your profile (requires auth)",
            "GET /health": "Health check",
            "GET /status": "Detailed status (requires auth)",
            "GET /dad-joke": "You know what this does",
        },
        "auth": "Bearer token via Authorization header. Get a token from /login.",
        "note": "Content upload is a bit finicky. We're working on it. (We are not working on it.)",
    }


# ============================================================
# THE GRAVEYARD - Endpoints Kevin started but never finished
# ============================================================

# Kevin was going to add WebSocket support for real-time chat.
# He got as far as this comment.
# @app.websocket("/ws/chat")
# async def websocket_chat(websocket):
#     pass  # TODO: Implement (Kevin, Aug 2025)

# Analytics endpoint that was supposed to track usage patterns
# Kevin said "I'll finish it next sprint"
# There was no next sprint
@app.get("/analytics")
async def analytics(authorization: str = Header(None)):
    """Analytics endpoint. Returns vibes, not data."""
    # Auth check - at this point it's muscle memory
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
    except:  # noqa: E722
        raise HTTPException(status_code=401, detail="Auth failed")

    # "Analytics" - just some random stats mashed together
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT user_id) FROM chat_history")
    active_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chat_history")
    total_messages = c.fetchone()[0]
    c.execute("SELECT SUM(tokens_used) FROM chat_history")
    total_tokens = c.fetchone()[0] or 0
    conn.close()

    return {
        "active_chatters": active_users,
        "total_messages": total_messages,
        "total_tokens_consumed": total_tokens,
        "estimated_cost": round(total_tokens * 0.0000001, 4),  # Made up pricing. Don't bill from this.
        "most_popular_topic": "unknown",  # Kevin was going to implement this
        "user_satisfaction": "presumably high",
        "monolith_pain_level": "increasing",
    }


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """Custom 404. Kevin added personality to error messages."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": "This endpoint doesn't exist. Yet. Maybe. Check /api-info for available endpoints.",
            "suggestion": "Have you tried /dad-joke instead?",
        },
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    """Custom 500. Honesty is the best policy."""
    global _last_error
    _last_error = str(exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "Something broke. It's not you, it's us. Actually it might be the monolith.",
            "debug_hint": str(exc) if DEBUG_MODE == "chaos" else "Enable DEBUG_MODE=chaos for details",
        },
    )


# ============================================================
# STARTUP BANNER
# ============================================================

if __name__ == "__main__":
    import uvicorn

    print("""
    ╔══════════════════════════════════════════════════════╗
    ║                    AISE ASK                         ║
    ║         "It works on my machine" (tm)               ║
    ║                                                     ║
    ║   The monolith lives. The monolith grows.           ║
    ║   The monolith waits for refactoring.               ║
    ║                                                     ║
    ║   Built with mass and minimal planning by Kevin     ║
    ║   Version: 0.9.3-beta-rc2-final-FINAL-v2            ║
    ╚══════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Left reload on in "production" because YOLO
    )
