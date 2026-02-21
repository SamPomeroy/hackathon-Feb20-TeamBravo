"""
Content Service
Handles: content upload, search, listing
Port: 8003

Fixes from monolith:
- BUG FIX 1: upload_content was writing to sqlite3.connect(":memory:") — an in-memory
  DB that vanishes on close. Now writes to the real persistent DATABASE_PATH.
- BUG FIX 2: search used a global _content_cache that was never invalidated after uploads.
  Now queries the DB directly on every search — no cache, no staleness.
- No copy-pasted auth — gateway injects x-user-id header
- No bare except: pass — errors are logged and raised properly
"""

import json
import os
import uuid

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from models import ContentUpload, ContentSearch
from database import init_db, get_db, DBContent

def safe_json_loads(data: str) -> dict:
    if not data:
        return {}
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return {}

# ── App ───────────────────────────────────────────────────────────────────────
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("[content-service] Started on port 8003")
    yield

app = FastAPI(title="Content Service", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/content/upload")
async def upload_content(
    content: ContentUpload,
    x_user_id: str = Header(None),
    db: Session = Depends(get_db),
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing user identity headers from gateway")

    content_id = str(uuid.uuid4())
    metadata_str = json.dumps(content.metadata) if content.metadata else None

    # FIX: use get_conn() which connects to DATABASE_PATH (the real file),
    # NOT sqlite3.connect(":memory:") like the monolith did.
    try:
        new_content = DBContent(
            id=content_id,
            title=content.title,
            body=content.body,
            content_type=content.content_type,
            metadata_json=metadata_str,
            uploaded_by=x_user_id,
            is_indexed=1
        )
        db.add(new_content)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    # FIX: no cache to invalidate — search hits the DB directly now, so new content
    # is immediately searchable without any extra steps.

    return {
        "message": "Content uploaded successfully",
        "content_id": content_id,
        "title": content.title,
        "status": "indexed",  # actually true this time 🎉
    }


@app.post("/content/upload-file")
async def upload_content_file(
    file: UploadFile = File(...),
    x_user_id: str = Header(None),
    db: Session = Depends(get_db),
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing user identity headers from gateway")

    try:
        raw = await file.read()
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {str(e)}")

    items = data if isinstance(data, list) else [data]
    uploaded_ids = []

    try:
        for item in items:
            if not item.get("title") or not item.get("body"):
                continue  # skip malformed items, don't blow up the whole batch
            content_id = str(uuid.uuid4())
            metadata = item.get("metadata")
            
            new_content = DBContent(
                id=content_id,
                title=item["title"],
                body=item["body"],
                content_type=item.get("content_type", "lesson"),
                metadata_json=json.dumps(metadata) if metadata else None,
                uploaded_by=x_user_id,
                is_indexed=1
            )
            db.add(new_content)
            uploaded_ids.append(content_id)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

    return {
        "message": f"Successfully uploaded {len(uploaded_ids)} content items",
        "count": len(uploaded_ids),
        "content_ids": uploaded_ids,
        "status": "indexed",
    }


@app.post("/content/search")
async def search_content(
    search: ContentSearch,
    x_user_id: str = Header(None),
    db: Session = Depends(get_db),
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing user identity headers from gateway")

    # FIX: query the DB directly every time — no stale cache.
    # it_works_dont_ask_why() is gone. The DB is the source of truth.
    rows = db.query(DBContent).filter(DBContent.is_indexed == 1).all()

    query_lower = search.query.lower()
    query_words = set(query_lower.split())

    results = []
    for row in rows:
        title_lower = (row.title or "").lower()
        body_lower = (row.body or "").lower()
        metadata = safe_json_loads(row.metadata_json)
        tags = metadata.get("tags", [])

        score = 0
        for word in query_words:
            if word in title_lower:
                score += 10
            if word in body_lower:
                score += 1
            if any(word in tag for tag in tags):
                score += 5

        if score > 0:
            body = row.body or ""
            results.append({
                "id": row.id,
                "title": row.title,
                "body": body[:200] + "..." if len(body) > 200 else body,
                "content_type": row.content_type,
                "score": score,
                "metadata": metadata,
            })

    results.sort(key=lambda x: x["score"], reverse=True)

    # If nothing matched, return top items (same fallback behavior as monolith)
    if not results and rows:
        for row in rows[: search.limit]:
            body = row.body or ""
            results.append({
                "id": row.id,
                "title": row.title,
                "body": body[:200] + "..." if len(body) > 200 else body,
                "content_type": row.content_type,
                "score": 0,
                "metadata": safe_json_loads(row.metadata_json),
            })

    return {
        "results": results[: search.limit],
        "total": len(results),
        "query": search.query,
        "source": "database",  # not cache — for real this time
    }


@app.get("/content")
async def list_content(
    x_user_id: str = Header(None),
    db: Session = Depends(get_db),
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing user identity headers from gateway")

    rows = db.query(DBContent).order_by(DBContent.created_at.desc()).all()

    content_list = []
    for row in rows:
        body = row.body or ""
        content_list.append({
            "id": row.id,
            "title": row.title,
            "body": body[:200] + "..." if len(body) > 200 else body,
            "content_type": row.content_type,
            "metadata": safe_json_loads(row.metadata_json),
            "created_at": row.created_at,
        })

    return {"content": content_list, "total": len(content_list)}


@app.get("/content/internal")
async def list_content_internal(db: Session = Depends(get_db)):
    """
    Internal endpoint for the chat service to fetch content for system prompt context.
    No auth required — only reachable service-to-service (not exposed via gateway).
    """
    rows = db.query(DBContent)\
        .filter(DBContent.is_indexed == 1)\
        .order_by(DBContent.created_at.desc())\
        .limit(10)\
        .all()
    
    return {"content": [{"id": row.id, "title": row.title, "body": row.body, "content_type": row.content_type} for row in rows]}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "content"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)
