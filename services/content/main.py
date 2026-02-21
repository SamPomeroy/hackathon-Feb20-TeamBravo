"""
Content Service — upload, search, and list lesson content.
Bugs fixed:
  - Upload writes to REAL database (not :memory:)
  - Search queries DB directly every time (no stale cache)
  - File upload actually persists content
"""

import json
import uuid

from fastapi import FastAPI, HTTPException, Header, UploadFile, File

from database import get_conn, init_db
from models import ContentUpload, ContentSearch

app = FastAPI(title="Content Service", version="1.0.0")


@app.on_event("startup")
async def startup():
    init_db()


# --------------- Endpoints ---------------

@app.post("/content/upload")
async def upload_content(content: ContentUpload, x_user_id: str = Header(None)):
    """Upload content — FIX: writes to the real DB file, not :memory:."""
    user_id = x_user_id or "unknown"
    content_id = str(uuid.uuid4())

    conn = get_conn()  # REAL database
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO content (id, title, body, content_type, metadata, uploaded_by, is_indexed) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (content_id, content.title, content.body, content.content_type,
             json.dumps(content.metadata) if content.metadata else None, user_id),
        )
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    conn.close()

    return {
        "message": "Content uploaded successfully",
        "content_id": content_id,
        "title": content.title,
        "status": "indexed",
    }


@app.post("/content/upload-file")
async def upload_content_file(file: UploadFile = File(...), x_user_id: str = Header(None)):
    """Upload content from JSON file — FIX: actually persists to DB."""
    user_id = x_user_id or "unknown"

    try:
        file_content = await file.read()
        data = json.loads(file_content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read file")

    conn = get_conn()
    c = conn.cursor()

    def insert_one(item: dict) -> str:
        cid = str(uuid.uuid4())
        c.execute(
            "INSERT INTO content (id, title, body, content_type, metadata, uploaded_by, is_indexed) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (cid, item.get("title", "Untitled"), item.get("body", ""),
             item.get("content_type", "lesson"),
             json.dumps(item.get("metadata")) if item.get("metadata") else None,
             user_id),
        )
        return cid

    try:
        if isinstance(data, list):
            for item in data:
                insert_one(item)
            conn.commit()
            conn.close()
            return {"message": f"Successfully uploaded {len(data)} content items", "count": len(data), "status": "indexed"}
        elif isinstance(data, dict):
            cid = insert_one(data)
            conn.commit()
            conn.close()
            return {"message": "Content uploaded successfully", "content_id": cid, "status": "indexed"}
        else:
            conn.close()
            raise HTTPException(status_code=400, detail="JSON must be object or array")
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.post("/content/search")
async def search_content(search: ContentSearch, x_user_id: str = Header(None)):
    """Search content — FIX: queries DB directly every time (no stale cache)."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, title, body, content_type, metadata FROM content WHERE is_indexed = 1")
    rows = c.fetchall()
    conn.close()

    query_lower = search.query.lower()
    query_words = set(query_lower.split())

    results = []
    for row in rows:
        cid, title, body, ctype, meta_str = row
        metadata = json.loads(meta_str) if meta_str else {}
        title_lower = (title or "").lower()
        body_lower = (body or "").lower()

        score = 0
        for word in query_words:
            if word in title_lower:
                score += 10
            if word in body_lower:
                score += 1
            tags = metadata.get("tags", [])
            if any(word in tag for tag in tags):
                score += 5

        if score > 0:
            results.append({
                "id": cid,
                "title": title,
                "body": body[:200] + "..." if body and len(body) > 200 else body,
                "content_type": ctype,
                "score": score,
                "metadata": metadata,
            })

    results.sort(key=lambda x: x["score"], reverse=True)

    if not results and rows:
        for row in rows[:search.limit]:
            cid, title, body, ctype, meta_str = row
            metadata = json.loads(meta_str) if meta_str else {}
            results.append({
                "id": cid,
                "title": title,
                "body": body[:200] + "..." if body and len(body) > 200 else body,
                "content_type": ctype,
                "score": 0,
                "metadata": metadata,
            })

    return {"results": results[:search.limit], "total": len(results), "query": search.query, "source": "database"}


@app.get("/content")
async def list_content(x_user_id: str = Header(None)):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, title, body, content_type, metadata, created_at FROM content ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()

    content_list = [
        {
            "id": r[0],
            "title": r[1],
            "body": r[2][:200] + "..." if r[2] and len(r[2]) > 200 else r[2],
            "content_type": r[3],
            "metadata": json.loads(r[4]) if r[4] else {},
            "created_at": r[5],
        }
        for r in rows
    ]
    return {"content": content_list, "total": len(content_list)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "content"}


if __name__ == "__main__":
    import uvicorn
    print("Content Service starting on port 8003")
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)
