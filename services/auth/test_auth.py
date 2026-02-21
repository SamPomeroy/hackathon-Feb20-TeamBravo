"""
Tests for Auth Service — registration, login, token verification, bcrypt.
Run with: pytest test_auth.py -v
"""

import os
import sys
import sqlite3
import pytest
from fastapi.testclient import TestClient

# Ensure a SECRET_KEY exists for testing
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-1234567890")

from main import app
from database import DATABASE_PATH, init_db, get_conn
from main import hash_password, check_password

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    """Wipe users table before each test so tests are independent."""
    init_db()
    conn = get_conn()
    conn.execute("DELETE FROM users")
    conn.commit()
    conn.close()
    yield


# --------------- Registration ---------------

def test_register_success():
    resp = client.post("/register", json={"username": "alice", "password": "pass1234"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "alice"
    assert "token" in data
    assert "user_id" in data


def test_register_short_username():
    resp = client.post("/register", json={"username": "ab", "password": "pass1234"})
    assert resp.status_code == 400


def test_register_short_password():
    resp = client.post("/register", json={"username": "alice", "password": "abc"})
    assert resp.status_code == 400


def test_register_duplicate():
    client.post("/register", json={"username": "alice", "password": "pass1234"})
    resp = client.post("/register", json={"username": "alice", "password": "other"})
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"]


# --------------- Login ---------------

def test_login_success():
    client.post("/register", json={"username": "bob", "password": "secure123"})
    resp = client.post("/login", json={"username": "bob", "password": "secure123"})
    assert resp.status_code == 200
    assert "token" in resp.json()


def test_login_wrong_password():
    client.post("/register", json={"username": "bob", "password": "secure123"})
    resp = client.post("/login", json={"username": "bob", "password": "wrong"})
    assert resp.status_code == 401


def test_login_nonexistent_user():
    resp = client.post("/login", json={"username": "ghost", "password": "nope"})
    assert resp.status_code == 401


# --------------- Token verification ---------------

def test_verify_valid_token():
    reg = client.post("/register", json={"username": "carol", "password": "test1234"})
    token = reg.json()["token"]
    resp = client.post("/verify", json={"token": token})
    assert resp.status_code == 200
    assert resp.json()["valid"] is True
    assert resp.json()["username"] == "carol"


def test_verify_invalid_token():
    resp = client.post("/verify", json={"token": "garbage.token.here"})
    assert resp.status_code == 401


def test_verify_bearer_prefix():
    reg = client.post("/register", json={"username": "dave", "password": "test1234"})
    token = reg.json()["token"]
    resp = client.post("/verify", json={"token": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


# --------------- Bcrypt check ---------------

def test_bcrypt_hashing():
    hashed = hash_password("mypassword")
    assert hashed != "mypassword"
    assert check_password("mypassword", hashed) is True
    assert check_password("wrong", hashed) is False


# --------------- Health ---------------

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "auth"
