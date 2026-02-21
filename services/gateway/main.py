import os
import random

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from middleware import verify_token

AUTH_SERVICE_URL    = os.getenv("AUTH_SERVICE_URL",    "http://localhost:8001")
CHAT_SERVICE_URL    = os.getenv("CHAT_SERVICE_URL",    "http://localhost:8002")
CONTENT_SERVICE_URL = os.getenv("CONTENT_SERVICE_URL", "http://localhost:8003")

TIMEOUT = 30.0

app = FastAPI(
    title="AISE ASK — API Gateway",
    description="Routes requests to Auth, Chat, and Content services.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def proxy(request: Request, target_url: str, extra_headers: dict = None):
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "authorization", "content-length")
    }
    if extra_headers:
        headers.update(extra_headers)

    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=dict(request.query_params),
            )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"Service unavailable ({target_url})")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Service timed out")


@app.get("/")
async def root():
    return {"app": "AISE ASK", "version": "1.0.0", "status": "operational", "docs": "/docs"}


@app.get("/health")
async def health():
    results = {}
    for name, url in [("auth", AUTH_SERVICE_URL), ("chat", CHAT_SERVICE_URL), ("content", CONTENT_SERVICE_URL)]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{url}/health")
                results[name] = "ok" if resp.status_code == 200 else "degraded"
        except Exception:
            results[name] = "unreachable"
    overall = "ok" if all(v == "ok" for v in results.values()) else "degraded"
    return {"status": overall, "services": results}


@app.post("/register")
async def register(request: Request):
    return await proxy(request, f"{AUTH_SERVICE_URL}/register")


@app.post("/login")
async def login(request: Request):
    return await proxy(request, f"{AUTH_SERVICE_URL}/login")


@app.get("/dad-joke")
async def dad_joke():
    jokes = [
        "Why do programmers prefer dark mode? Because light attracts bugs.",
        "A SQL query walks into a bar, walks up to two tables and asks... 'Can I JOIN you?'",
        "Why do microservices never get lonely? Because they're always in a cluster.",
        "What's a monolith's favorite song? 'All By Myself'.",
        "Why did the REST API break up with SOAP? Too much baggage.",
    ]
    return {"joke": random.choice(jokes), "groaned": True, "dad_approved": True}


@app.post("/chat")
async def chat(request: Request):
    payload = await verify_token(request)
    user_headers = {
        "x-user-id": payload["user_id"],
        "x-username": payload["username"],
        "x-user-role": payload.get("role", "fellow"),
    }
    return await proxy(request, f"{CHAT_SERVICE_URL}/chat", extra_headers=user_headers)


@app.get("/chat/history")
async def chat_history(request: Request):
    payload = await verify_token(request)
    user_headers = {"x-user-id": payload["user_id"], "x-username": payload["username"]}
    return await proxy(request, f"{CHAT_SERVICE_URL}/chat/history", extra_headers=user_headers)


@app.post("/content/upload")
async def upload_content(request: Request):
    payload = await verify_token(request)
    return await proxy(request, f"{CONTENT_SERVICE_URL}/content/upload", extra_headers={"x-user-id": payload["user_id"]})


@app.post("/content/upload-file")
async def upload_content_file(request: Request):
    payload = await verify_token(request)
    return await proxy(request, f"{CONTENT_SERVICE_URL}/content/upload-file", extra_headers={"x-user-id": payload["user_id"]})


@app.post("/content/search")
async def search_content(request: Request):
    payload = await verify_token(request)
    return await proxy(request, f"{CONTENT_SERVICE_URL}/content/search", extra_headers={"x-user-id": payload["user_id"]})


@app.get("/content")
async def list_content(request: Request):
    payload = await verify_token(request)
    return await proxy(request, f"{CONTENT_SERVICE_URL}/content", extra_headers={"x-user-id": payload["user_id"]})


@app.get("/me")
async def get_profile(request: Request):
    payload = await verify_token(request)
    return {"user_id": payload["user_id"], "username": payload["username"], "role": payload.get("role", "fellow")}


@app.exception_handler(404)
async def not_found(request: Request, exc: HTTPException):
    return JSONResponse(status_code=404, content={"error": "Not Found", "message": "Check /docs for available endpoints."})


@app.exception_handler(500)
async def server_error(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "Internal Server Error", "message": str(exc)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
