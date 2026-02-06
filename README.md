# Mono Meltdown

> You inherited a monolith. Your mission: break it apart before it breaks you.

**AISE ASK** is a chatbot for the AI Safety & Engineering fellowship program. It handles user authentication, AI-powered chat (via Groq), and lesson content management. It was built by a contractor named Kevin who has since left the company. Everything is in one file. There are bugs. There are secrets hardcoded in the source. There is a function called `it_works_dont_ask_why()`. Welcome to your hackathon.

## Quick Setup

Get the monolith running in under 10 minutes.

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A [Groq API key](https://console.groq.com) (free tier works)

### Steps

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd aise2026-hackathon2-mono-meltdown

# 2. Install dependencies
uv pip install -r requirements.txt
# or: pip install -r requirements.txt

# 3. Set up environment variables
cp .env.example .env
# Edit .env and add your GROQ_API_KEY

# 4. Run the monolith
python main.py
```

The app runs on `http://localhost:8000`. Interactive API docs are at `http://localhost:8000/docs`.

### Verify It Works

```bash
# Register a user
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "test1234"}'

# Copy the token from the response, then chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{"message": "What topics does the AISE program cover?"}'
```

## The Monolith

AISE ASK lives entirely in `main.py` (~1,270 lines). It's a FastAPI application that handles:

- **User authentication** — Registration, login, JWT tokens (with MD5 password hashing)
- **AI chat** — Sends messages to Groq's LLM API with conversation history and program context
- **Content management** — Stores lesson content, supports upload and search (both broken)
- **System status** — Health checks, analytics, user profiles

It uses SQLite for persistence, global mutable state for sessions and caching, and has the JWT secret key hardcoded in the source code. Every endpoint that requires auth has the token verification logic copy-pasted inline rather than extracted into middleware.

## Your Mission

Decompose this monolith into **4 microservices**:

### 1. Auth Service
- User registration and login
- JWT token creation and validation
- Password hashing (fix MD5 → bcrypt)
- Move the hardcoded `SECRET_KEY` to an environment variable

### 2. Chat Service
- Groq API integration
- Conversation history (load/save)
- Session management
- System prompt construction with content context

### 3. Content Service
- Content upload — **fix the bug** (currently writes to an in-memory database that vanishes)
- Content search — fix stale cache issue (cache is never invalidated after new uploads)
- Content listing and storage
- File upload ingestion

### 4. API Gateway
- Routes incoming requests to the appropriate service
- Handles CORS configuration
- Auth middleware (replace the copy-pasted token verification)
- Unified error handling

## Hackathon Schedule

**Saturday, February 21, 2026** | Virtual (cameras required) | Teams of 3 (pre-assigned)

### Working Time: 10:00 AM - 3:00 PM ET (5 hours)

| Phase | Time | What to Do |
|-------|------|------------|
| **1. Discovery & Setup** | 45 min | Run the monolith. Read `main.py` top to bottom. Hit every endpoint. Find the bugs and anti-patterns. |
| **2. Planning & Issue Creation** | 45 min | Set up your GitHub Project board. Create issues with labels and acceptance criteria. Assign work to team members. Sketch your architecture. |
| **3. Implementation** | 2 hr 30 min | Build microservices on feature branches. Open PRs. Review each other's code. |
| **4. Integration & Testing** | 30 min | Wire services together through the gateway. Test end-to-end. Verify the content upload bug is fixed. |
| **5. Demo Prep** | 30 min | Prepare a short demo showing the before (monolith) and after (microservices). |

### Presentations & Judging: 3:00 PM - 5:00 PM ET

Each team gets **5-6 minutes** to demo their work, followed by Q&A from judges. Every team member must present and be prepared to answer questions about their contributions and architectural decisions.

## GitHub Workflow Requirements

These are **graded**. Follow them throughout the hackathon.

### Project Board
- Create a **GitHub Project** board with columns: **To Do**, **In Progress**, **Done**
- Every issue should move across the board as work progresses

### Issues
- Create a **GitHub Issue** for each piece of work
- Each issue must have:
  - A descriptive title
  - Acceptance criteria (what "done" looks like)
  - At least one label (e.g., `auth`, `chat`, `content`, `gateway`, `bug`, `refactor`)
- Assign issues to team members

### Branches
- Use **feature branches** — never commit directly to `main`
- Naming convention:
  - `feature/auth-service`
  - `feature/chat-service`
  - `feature/content-service`
  - `feature/api-gateway`
  - `fix/content-upload`
  - `fix/password-hashing`
  - `refactor/auth-middleware`

### Pull Requests
- Every branch merges via a **Pull Request**
- Link PRs to their issues (use `Closes #XX` in the PR description)
- Use the provided PR template (`.github/PULL_REQUEST_TEMPLATE.md`)
- **At least 1 code review** per PR before merging

## Writing Good Issues

Your team decides what issues to create. Each issue should look something like this:

> **Title:** Extract auth logic into Auth Service
>
> **Labels:** `auth`, `refactor`
>
> **Description:**
> Move registration and login endpoints out of `main.py` into a standalone Auth Service with its own router.
>
> **Acceptance Criteria:**
> - Auth Service runs independently with its own entry point
> - `/register` and `/login` work the same as before
> - Token verification is middleware, not copy-pasted
> - No hardcoded secrets in source code

## Evaluation Criteria

### Passing (70%)

You demonstrated that you understand the monolith's problems and started fixing them.

- At least **1 microservice** fully extracted and running independently
- GitHub Project board exists with issues that have labels and assignments
- PRs were opened with descriptions and linked to issues
- Known bugs are identified (even if not all are fixed)
- Team can demo the working service and explain their approach

### Good (80%)

You made real architectural progress and followed solid engineering practices.

- **2+ microservices** extracted with clear boundaries between them
- Proper error handling (no more bare `except: pass`)
- Secrets moved out of source code and into environment variables
- At least one bug fix (content upload, stale search, or MD5 passwords)
- Code reviews on PRs — not just rubber stamps, actual feedback
- Each team member can explain what they built and why

### Excellent (90%+)

You shipped a well-architected system that's meaningfully better than the monolith.

- **Full separation** into distinct services that communicate via APIs
- All major bugs fixed (content upload persists, search returns fresh results, bcrypt passwords)
- Auth middleware replaces copy-pasted token verification
- No hardcoded secrets, no unnecessary global state
- Tests for at least one service
- Clean, well-organized GitHub history — issues, branches, PRs, and reviews tell the story of your work
- Polished demo with clear before/after comparison

## API Reference

All endpoints in the current monolith:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/` | No | Welcome message and links |
| `GET` | `/health` | No | Health check (DB status, uptime, cache size) |
| `GET` | `/api-info` | No | Lists all available endpoints |
| `GET` | `/dad-joke` | No | Returns a random programming dad joke |
| `POST` | `/register` | No | Register a new user, returns JWT token |
| `POST` | `/login` | No | Login with username/password, returns JWT token |
| `POST` | `/chat` | Yes | Send a message to the AI assistant |
| `GET` | `/chat/history` | Yes | Get chat history (optional `session_id` and `limit` params) |
| `POST` | `/content/upload` | Yes | Upload lesson content (broken — saves to in-memory DB) |
| `POST` | `/content/upload-file` | Yes | Upload content from a JSON file (broken — doesn't persist) |
| `POST` | `/content/search` | Yes | Search content by keyword (uses stale cache) |
| `GET` | `/content` | Yes | List all content |
| `GET` | `/me` | Yes | Get current user profile and chat stats |
| `GET` | `/status` | Yes | Detailed system status (sessions, DB counts, debug log) |
| `GET` | `/analytics` | Yes | Usage analytics (user count, messages, tokens) |

**Auth format:** `Authorization: Bearer <token>` header. Get a token from `/register` or `/login`.

## Seed Data

The `seed_data/` directory contains sample lesson files for testing content upload:

```
seed_data/
├── lesson_ai_safety_fundamentals.json
├── lesson_building_agents.json
├── lesson_prompt_engineering.json
└── lesson_red_teaming.json
```

Each file is a JSON object with `title`, `body`, `content_type`, and `metadata` fields. Use these to test your content upload endpoint once you fix it:

```bash
# Upload a single lesson (after fixing the upload bug)
curl -X POST http://localhost:8000/content/upload \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d @seed_data/lesson_ai_safety_fundamentals.json

# Or upload via file endpoint
curl -X POST http://localhost:8000/content/upload-file \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@seed_data/lesson_ai_safety_fundamentals.json"
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | Your Groq API key ([get one here](https://console.groq.com)) |
| `DEBUG_MODE` | No | Set to `chaos` for entertaining debug logs |

## AI Policy

AI tools (Claude, ChatGPT, Copilot, etc.) are permitted. However, you may **not** paste the entire codebase and ask an AI to refactor it for you. Every architectural decision must be understood and defendable — during presentations, each team member will be asked to explain their contributions and the reasoning behind their choices.

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Groq API Documentation](https://console.groq.com/docs)
- [GitHub Projects Documentation](https://docs.github.com/en/issues/planning-and-tracking-with-projects)
- See `FAQ.md` for common questions and troubleshooting
