"""
Tests for the content service bug fixes.
Validates: real DB persistence, file upload INSERTs, cache invalidation,
and proper exception handling (no bare excepts).
"""

import json
import os
import time
import tempfile

import jwt
import pytest
from fastapi.testclient import TestClient

# Point the DB at a temp file so tests don't touch production data
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
TEST_DB_PATH = _test_db.name
_test_db.close()

os.environ["CONTENT_DB_PATH"] = TEST_DB_PATH

from main import app  # noqa: E402 (must come after env override)
import database  # noqa: E402

# Ensure the table exists (TestClient doesn't fire startup events)
database.init_db()

client = TestClient(app)


# ── Helpers ──────────────────────────────────────────────────

def _auth_header(user_id: str | None = "test-user") -> dict:
    if user_id is None:
        return {}
    return {"x-user-id": user_id}


def _count_rows() -> int:
    db = database.get_session()
    n = db.query(database.DBContent).count()
    db.close()
    return n


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean_db():
    """Wipe the content table and cache between tests."""
    db = database.get_session()
    db.query(database.DBContent).delete()
    db.commit()
    db.close()
    database._content_cache = None
    yield


# ── Bug 1: Content upload must persist to real DB ────────────

class TestContentUploadPersistence:
    def test_upload_persists_to_db(self):
        """Uploading content should INSERT into the real DB, not an in-memory one."""
        before = _count_rows()
        resp = client.post(
            "/content/upload",
            json={"title": "Test Lesson", "body": "Some body text"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert _count_rows() == before + 1

    def test_upload_appears_in_list(self):
        """Uploaded content should be retrievable via GET /content."""
        client.post(
            "/content/upload",
            json={"title": "Findable Lesson", "body": "You should find me"},
            headers=_auth_header(),
        )
        resp = client.get("/content", headers=_auth_header())
        titles = [c["title"] for c in resp.json()["content"]]
        assert "Findable Lesson" in titles


# ── Bug 2: File upload must INSERT rows ──────────────────────

class TestFileUploadInserts:
    def test_file_upload_list_persists(self):
        """Uploading a JSON array should INSERT all items."""
        data = [
            {"title": "File Item 1", "body": "Body 1"},
            {"title": "File Item 2", "body": "Body 2"},
        ]
        file_bytes = json.dumps(data).encode()
        resp = client.post(
            "/content/upload-file",
            files={"file": ("test.json", file_bytes, "application/json")},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 2
        assert _count_rows() == 2

    def test_file_upload_dict_persists(self):
        """Uploading a single JSON object should INSERT one item."""
        data = {"title": "Single Item", "body": "Just one"}
        file_bytes = json.dumps(data).encode()
        resp = client.post(
            "/content/upload-file",
            files={"file": ("single.json", file_bytes, "application/json")},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert _count_rows() == 1


# ── Bug 3: Cache must be invalidated after upload ────────────

class TestCacheInvalidation:
    def test_search_finds_newly_uploaded_content(self):
        """After upload, a search should return the new content (cache refreshed)."""
        client.post(
            "/content/upload",
            json={"title": "Cache Test", "body": "cache invalidation check"},
            headers=_auth_header(),
        )
        resp = client.post(
            "/content/search",
            json={"query": "cache invalidation"},
            headers=_auth_header(),
        )
        titles = [r["title"] for r in resp.json()["results"]]
        assert "Cache Test" in titles

    def test_file_upload_invalidates_cache(self):
        """File upload should also invalidate the cache."""
        data = [{"title": "File Cache Test", "body": "file cache body"}]
        file_bytes = json.dumps(data).encode()
        client.post(
            "/content/upload-file",
            files={"file": ("c.json", file_bytes, "application/json")},
            headers=_auth_header(),
        )
        resp = client.post(
            "/content/search",
            json={"query": "file cache"},
            headers=_auth_header(),
        )
        titles = [r["title"] for r in resp.json()["results"]]
        assert "File Cache Test" in titles


# ── LRU Caching and Write-Through Cache Tests ────────────────

class TestLRUCache:
    def test_cache_initialization_and_retrieval(self):
        """Test that get_cached_content initializes the cache from the DB."""
        client.post(
            "/content/upload",
            json={"title": "Init 1", "body": "Body 1"},
            headers=_auth_header(),
        )
        client.post(
            "/content/upload",
            json={"title": "Init 2", "body": "Body 2"},
            headers=_auth_header(),
        )
        
        database._content_cache = None
        cache = database.get_cached_content()
        assert len(cache) == 2
        titles = [item["title"] for item in cache.values()]
        assert "Init 1" in titles
        assert "Init 2" in titles

    def test_lru_eviction(self, monkeypatch):
        """Test that the cache successfully evicts the least recently used items."""
        monkeypatch.setattr(database, "MAX_CACHE_SIZE", 3)
        
        client.post("/content/upload", json={"title": "Item 1", "body": "B1"}, headers=_auth_header())
        time.sleep(0.01)
        client.post("/content/upload", json={"title": "Item 2", "body": "B2"}, headers=_auth_header())
        time.sleep(0.01)
        client.post("/content/upload", json={"title": "Item 3", "body": "B3"}, headers=_auth_header())
        
        cache = database.get_cached_content()
        assert len(cache) == 3
        
        client.post("/content/upload", json={"title": "Item 4", "body": "B4"}, headers=_auth_header())
        
        cache = database.get_cached_content()
        assert len(cache) == 3
        titles = [item["title"] for item in cache.values()]
        assert "Item 4" in titles
        assert "Item 1" not in titles

    def test_write_through_cache_inserts_without_refresh(self):
        """Test that uploading triggers a write-through update, avoiding full refresh."""
        database.get_cached_content(force_refresh=True)
        assert database._content_cache is not None
        assert len(database._content_cache) == 0
        
        resp = client.post("/content/upload", json={"title": "Write Through", "body": "B"}, headers=_auth_header())
        assert resp.status_code == 200
        content_id = resp.json()["content_id"]
        
        assert content_id in database._content_cache
        assert database._content_cache[content_id]["title"] == "Write Through"
        
        search_resp = client.post("/content/search", json={"query": "Write Through"}, headers=_auth_header())
        titles = [r["title"] for r in search_resp.json()["results"]]
        assert "Write Through" in titles


# ── Bug 4: No bare excepts — proper error responses ─────────

class TestErrorHandling:
    def test_missing_auth_returns_401(self):
        resp = client.post("/content/upload", json={"title": "x", "body": "y"})
        assert resp.status_code == 401

    def test_invalid_auth_header_format(self):
        resp = client.post(
            "/content/upload",
            json={"title": "x", "body": "y"},
            headers={"Authorization": "Bearer some-token"},
        )
        assert resp.status_code == 401

    def test_bad_json_file_returns_400(self):
        resp = client.post(
            "/content/upload-file",
            files={"file": ("bad.json", b"not json at all", "application/json")},
            headers=_auth_header(),
        )
        assert resp.status_code == 400
