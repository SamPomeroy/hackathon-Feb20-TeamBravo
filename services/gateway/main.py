"""
API Gateway — single entry point, routes to Auth, Chat, and Content services.
Fixes from monolith:
  - Auth middleware replaces copy-pasted token verification
  - Unified CORS
  - Clean error handling
"""

import os
import sqlite3
import time
import random

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from middleware import verify_auth

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

AUTH_SERVICE = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")
CHAT_SERVICE = os.getenv("CHAT_SERVICE_URL", "http://localhost:8002")
CONTENT_SERVICE = os.getenv("CONTENT_SERVICE_URL", "http://localhost:8003")

CHAT_DB_PATH = os.getenv("CHAT_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "chat", "chat.db"))

app = FastAPI(title="AISE ASK Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_system_start_time = time.time()


# --------------- Public routes ---------------

@app.get("/")
async def root():
    return {
        "app": "AISE ASK",
        "tagline": "Your AI Safety & Engineering Program Assistant",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health():
    statuses = {}
    for name, url in [("auth", AUTH_SERVICE), ("chat", CHAT_SERVICE), ("content", CONTENT_SERVICE)]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{url}/health")
                statuses[name] = r.json().get("status", "unknown")
        except Exception:
            statuses[name] = "unreachable"
    return {
        "status": "ok",
        "services": statuses,
        "uptime_seconds": round(time.time() - _system_start_time, 2),
    }


@app.get("/api-info")
async def api_info():
    return {
        "endpoints": {
            "POST /register": "Register a new user",
            "POST /login": "Login and get JWT token",
            "POST /chat": "Send a message to AISE ASK (requires auth)",
            "GET /chat/history": "Get your chat history (requires auth)",
            "POST /content/upload": "Upload lesson content (requires auth)",
            "POST /content/upload-file": "Upload content from JSON file (requires auth)",
            "POST /content/search": "Search content (requires auth)",
            "GET /content": "List all content (requires auth)",
            "GET /me": "Get your profile (requires auth)",
            "GET /health": "Health check",
            "GET /status": "Detailed status (requires auth)",
            "GET /analytics": "Usage analytics (requires auth)",
            "GET /dad-joke": "A programming dad joke",
        },
        "auth": "Bearer token via Authorization header. Get a token from /register or /login.",
    }


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
]


@app.get("/dad-joke")
async def dad_joke():
    return {"joke": random.choice(DAD_JOKES), "groaned": True, "dad_approved": True}


# --------------- Auth proxies ---------------

@app.post("/register")
async def register(request: Request):
    body = await request.json()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{AUTH_SERVICE}/register", json=body)
    return JSONResponse(status_code=resp.status_code, content=resp.json())


@app.post("/login")
async def login(request: Request):
    body = await request.json()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{AUTH_SERVICE}/login", json=body)
    return JSONResponse(status_code=resp.status_code, content=resp.json())


# --------------- Chat (auth required) ---------------

@app.post("/chat")
async def chat(request: Request):
    user = await verify_auth(request)
    body = await request.json()
    async with httpx.AsyncClient(timeout=35.0) as client:
        resp = await client.post(
            f"{CHAT_SERVICE}/chat",
            json=body,
            headers={"X-User-Id": user["user_id"], "X-Username": user["username"]},
        )
    return JSONResponse(status_code=resp.status_code, content=resp.json())


@app.get("/chat/history")
async def chat_history(request: Request, session_id: str = None, limit: int = 20):
    user = await verify_auth(request)
    params = {"limit": limit}
    if session_id:
        params["session_id"] = session_id
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{CHAT_SERVICE}/chat/history",
            params=params,
            headers={"X-User-Id": user["user_id"]},
        )
    return JSONResponse(status_code=resp.status_code, content=resp.json())


# --------------- Content (auth required) ---------------

@app.post("/content/upload")
async def content_upload(request: Request):
    user = await verify_auth(request)
    body = await request.json()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{CONTENT_SERVICE}/content/upload",
            json=body,
            headers={"X-User-Id": user["user_id"]},
        )
    return JSONResponse(status_code=resp.status_code, content=resp.json())


@app.post("/content/upload-file")
async def content_upload_file(request: Request, file: UploadFile = File(...)):
    user = await verify_auth(request)
    file_bytes = await file.read()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{CONTENT_SERVICE}/content/upload-file",
            files={"file": (file.filename, file_bytes, file.content_type)},
            headers={"X-User-Id": user["user_id"]},
        )
    return JSONResponse(status_code=resp.status_code, content=resp.json())


@app.post("/content/search")
async def content_search(request: Request):
    user = await verify_auth(request)
    body = await request.json()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{CONTENT_SERVICE}/content/search",
            json=body,
            headers={"X-User-Id": user["user_id"]},
        )
    return JSONResponse(status_code=resp.status_code, content=resp.json())


@app.get("/content")
async def content_list(request: Request):
    user = await verify_auth(request)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{CONTENT_SERVICE}/content",
            headers={"X-User-Id": user["user_id"]},
        )
    return JSONResponse(status_code=resp.status_code, content=resp.json())


# --------------- Profile, status, analytics ---------------

@app.get("/me")
async def get_profile(request: Request):
    user = await verify_auth(request)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{AUTH_SERVICE}/users/{user['user_id']}")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Could not fetch profile")
    profile = resp.json()

    # Chat stats from chat DB
    try:
        conn = sqlite3.connect(CHAT_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM chat_history WHERE user_id = ?", (user["user_id"],))
        chat_count = c.fetchone()[0]
        c.execute("SELECT SUM(tokens_used) FROM chat_history WHERE user_id = ?", (user["user_id"],))
        total_tokens = c.fetchone()[0] or 0
        conn.close()
        profile["stats"] = {"total_chats": chat_count, "total_tokens_used": total_tokens}
    except Exception:
        profile["stats"] = {"total_chats": 0, "total_tokens_used": 0}
    return profile


@app.get("/status")
async def status(request: Request):
    await verify_auth(request)
    return {
        "system": {"uptime_seconds": round(time.time() - _system_start_time, 2)},
    }


@app.get("/analytics")
async def analytics(request: Request):
    await verify_auth(request)
    try:
        conn = sqlite3.connect(CHAT_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT user_id) FROM chat_history")
        active_users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM chat_history")
        total_messages = c.fetchone()[0]
        c.execute("SELECT SUM(tokens_used) FROM chat_history")
        total_tokens = c.fetchone()[0] or 0
        conn.close()
    except Exception:
        active_users = total_messages = total_tokens = 0

    return {
        "active_chatters": active_users,
        "total_messages": total_messages,
        "total_tokens_consumed": total_tokens,
        "estimated_cost": round(total_tokens * 0.0000001, 4),
    }


# --------------- Error handlers ---------------

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=404, content={"error": "Not Found", "message": "Check /api-info for available endpoints."})


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "Internal Server Error", "message": str(exc)})


if __name__ == "__main__":
    import uvicorn
    print("API Gateway starting on port 8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
