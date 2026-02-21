import os
import httpx
from fastapi import HTTPException, Request

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")


async def verify_token(request: Request) -> dict:
    """
    Calls the auth service to verify the bearer token.
    Returns the decoded payload (user_id, username, role).
    Raises 401 if token is missing or invalid.

    This replaces the copy-pasted verify_token_inline() that appeared
    in literally every single endpoint in the monolith. Never again.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{AUTH_SERVICE_URL}/verify",
                json={"token": token},
            )
            if resp.status_code == 200:
                return resp.json()["payload"]
            else:
                detail = resp.json().get("detail", "Invalid token")
                raise HTTPException(status_code=401, detail=detail)
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Auth service unavailable")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")
