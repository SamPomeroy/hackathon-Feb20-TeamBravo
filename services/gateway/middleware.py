"""
Gateway auth middleware — single verify_token() replaces all copy-pasted auth checks.
"""

import os

import httpx
from fastapi import Request, HTTPException

AUTH_SERVICE = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")


async def verify_auth(request: Request) -> dict:
    """Verify the Authorization header by calling Auth Service's /verify endpoint.
    Returns user info dict on success, raises HTTPException on failure."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header required")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else auth_header
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{AUTH_SERVICE}/verify", json={"token": token})
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return resp.json()
