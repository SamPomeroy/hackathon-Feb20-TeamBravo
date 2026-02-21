# AISE ASK — Microservices

Decomposed from the Kevin monolith. Four services, each runs independently.

## Architecture

```
Client
  │
  ▼
Gateway (port 8000)  ← only port clients talk to
  ├── Auth Service    (port 8001)  — register, login, verify tokens
  ├── Chat Service    (port 8002)  — Groq API, conversation history
  └── Content Service (port 8003)  — upload, search, list content
```

## Setup

```bash
# 1. Copy env file
cp .env.example .env
# Edit .env — add your GROQ_API_KEY and SECRET_KEY

# 2. Install deps
pip install -r auth/requirements.txt
pip install -r chat/requirements.txt
pip install -r content/requirements.txt
pip install -r gateway/requirements.txt
```

## Running (4 terminals)

```bash
# Terminal 1 — Auth
cd auth && python main.py

# Terminal 2 — Chat
cd chat && python main.py

# Terminal 3 — Content
cd content && python main.py

# Terminal 4 — Gateway
cd gateway && python main.py
```

## Quick Test

```bash
# Register
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "securepass123"}'

# Chat (replace TOKEN)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TOKEN" \
  -d '{"message": "What is AI safety?"}'

# Upload content (actually persists now!)
curl -X POST http://localhost:8000/content/upload \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TOKEN" \
  -d '{"title": "Test", "body": "This actually saves.", "content_type": "lesson"}'

# Search (returns fresh results, no stale cache)
curl -X POST http://localhost:8000/content/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TOKEN" \
  -d '{"query": "test"}'

# Health
curl http://localhost:8000/health
```

## Running Tests

```bash
cd auth
pip install pytest
pytest test_auth.py -v
```

## Bugs Fixed vs Monolith

| Bug | Location | Fix |
|-----|----------|-----|
| Content upload wrote to `:memory:` | `content/main.py` | Uses `get_conn()` → real DB file |
| Search used stale never-invalidated cache | `content/main.py` | Queries DB directly every time |
| MD5 password hashing | `auth/main.py` | bcrypt via `hash_password()` |
| Hardcoded `SECRET_KEY` | `auth/main.py` | `os.getenv("SECRET_KEY")` — crashes if missing |
| Auth logic copy-pasted in every endpoint | `gateway/middleware.py` | Single `verify_auth()` used by gateway |
| Global mutable state | everywhere | Eliminated — DB is source of truth |
| Bare `except: pass` swallowing errors | everywhere | Explicit exception handling |
