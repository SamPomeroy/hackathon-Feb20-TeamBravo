"""
Content Service
Handles: content upload, search, listing
Port: 8003"""

import json
import os
import uuid

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from models import (
    ContentUpload, ContentSearch,
    UploadResponse, UploadFileResponse, SearchResponse, SearchResultItem,
    ListContentResponse, ContentItem, ListInternalContentResponse, InternalContentItem, HealthResponse
)
from database import init_db, get_db, DBContent, update_item_in_cache, get_cached_content
from exceptions import (
    AuthException, InvalidFileException, FileReadException,
    UploadFailedException, FileUploadFailedException
)
from dependencies import require_user_id

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

@app.post("/content/upload", response_model=UploadResponse)
async def upload_content(
    content: ContentUpload,
    x_user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
):

    content_id = str(uuid.uuid4())
    metadata_str = json.dumps(content.metadata) if content.metadata else None

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
        
        # Write-through cache: Update the cache gracefully without wiping it
        cached_item = {
            "id": content_id,
            "title": content.title,
            "body": content.body,
            "content_type": content.content_type,
            "metadata": content.metadata or {},
        }
        update_item_in_cache(cached_item)
        
    except Exception as e:
        db.rollback()
        raise UploadFailedException(str(e))

    return UploadResponse(
        message="Content uploaded successfully",
        content_id=content_id,
        title=content.title,
        status="indexed",
    )


@app.post("/content/upload-file", response_model=UploadFileResponse)
async def upload_content_file(
    file: UploadFile = File(...),
    x_user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
):

    try:
        raw = await file.read()
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise InvalidFileException()
    except Exception as e:
        raise FileReadException(str(e))

    items = data if isinstance(data, list) else [data]
    uploaded_ids = []
    new_cache_items = []

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
            
            # Prepare for write-through cache update
            new_cache_items.append({
                "id": content_id,
                "title": item["title"],
                "body": item["body"],
                "content_type": item.get("content_type", "lesson"),
                "metadata": metadata or {},
            })
            
        db.commit()
        
        # Write-through cache: add all new items to the existing memory cache
        for cache_item in new_cache_items:
            update_item_in_cache(cache_item)
            
    except Exception as e:
        db.rollback()
        raise FileUploadFailedException(str(e))

    return UploadFileResponse(
        message=f"Successfully uploaded {len(uploaded_ids)} content items",
        count=len(uploaded_ids),
        content_ids=uploaded_ids,
        status="indexed",
    )


@app.post("/content/search", response_model=SearchResponse)
async def search_content(
    search: ContentSearch,
    x_user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
):

    cached_content = get_cached_content()
    rows = list(cached_content.values())

    query_lower = search.query.lower()
    query_words = set(query_lower.split())

    results = []
    for row in rows:
        title_lower = (row.get("title") or "").lower()
        body_lower = (row.get("body") or "").lower()
        metadata = row.get("metadata") or {}
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
            body = row.get("body") or ""
            results.append(SearchResultItem(
                id=row.get("id"),
                title=row.get("title"),
                body=body[:200] + "..." if len(body) > 200 else body,
                content_type=row.get("content_type"),
                score=score,
                metadata=metadata,
            ))

    results.sort(key=lambda x: x.score, reverse=True)

    return SearchResponse(
        results=results[: search.limit],
        total=len(results),
        query=search.query,
        source="cache",
    )


@app.get("/content", response_model=ListContentResponse)
async def list_content(
    x_user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
):

    rows = db.query(DBContent).order_by(DBContent.created_at.desc()).all()

    content_list = []
    for row in rows:
        body = row.body or ""
        content_list.append(ContentItem(
            id=row.id,
            title=row.title,
            body=body[:200] + "..." if len(body) > 200 else body,
            content_type=row.content_type,
            metadata=safe_json_loads(row.metadata_json),
            created_at=row.created_at,
        ))

    return ListContentResponse(content=content_list, total=len(content_list))


@app.get("/content/internal", response_model=ListInternalContentResponse)
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
    
    return ListInternalContentResponse(
        content=[InternalContentItem(id=row.id, title=row.title, body=row.body, content_type=row.content_type) for row in rows]
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", service="content")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)
