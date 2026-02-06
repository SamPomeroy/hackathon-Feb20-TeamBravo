# FAQ

Common questions and troubleshooting for the Mono Meltdown hackathon.

---

### How do I get a Groq API key?

Go to [console.groq.com](https://console.groq.com), create a free account, and generate an API key. The free tier is sufficient for this hackathon. Add it to your `.env` file as `GROQ_API_KEY=your-key-here`.

---

### What's wrong with the content upload?

The `/content/upload` endpoint accepts your data and returns a success message, but the data doesn't actually persist. Look carefully at _what database_ the endpoint writes to. The response says `"status": "indexed"` — but is it? Try uploading content and then checking `/content` to see if it appears.

---

### Why does search return stale results?

The search endpoint reads from a cache (`_content_cache`) that gets populated once — when it's first accessed — and is never refreshed after that. Even if you fix the upload bug, newly uploaded content won't appear in search results until the cache is invalidated. Look at `it_works_dont_ask_why()` to understand how the cache works.

---

### What's the `it_works_dont_ask_why()` function doing?

It populates the `_content_cache` global variable by reading from the database — but only if the cache is empty. Once populated, the cache is never updated. This means new content uploaded after the first search will never appear in search results. The `time.sleep(0.01)` is a red herring — it doesn't serve a real purpose.

---

### What does the `DEBUG_MODE=chaos` env var do?

Set `DEBUG_MODE=chaos` in your `.env` file for entertaining debug logs. Every major operation prints a humorous message to the console (e.g., `[HOLD MY BEER] Token forged for testuser. The dark ritual is complete.`). It's useful for tracing request flow through the monolith, plus it's fun. It has no effect on functionality.

---

### Do we need to keep SQLite or can we switch databases?

You can switch! Your team chooses the database. Options include:
- **SQLite** — Simplest, already in use, no setup needed
- **PostgreSQL** (via Docker, Neon, or Supabase) — More production-realistic
- **Supabase** — Free tier, managed Postgres with a nice dashboard

Your database choice and reasoning are part of the evaluation. If you switch, make sure you can explain why.

---

### How do we split the database across services?

Each microservice should ideally own its own data. For example:
- **Auth Service** owns the `users` table
- **Chat Service** owns the `chat_history` table
- **Content Service** owns the `content` table

Whether you use separate database files, separate schemas, or separate databases entirely is a team decision. The key principle: a service should not directly access another service's data — it should go through that service's API.

---

### Do all 4 microservices need to be fully working?

No. Quality over quantity. A well-architected system with 2 solid microservices scores higher than 4 half-broken ones. That said, you should at least _plan_ the full architecture even if you don't finish implementing everything. The evaluation rubric weighs architecture and GitHub workflow higher than raw completion.

---

### Can we add new features or just refactor?

The primary goal is refactoring, but you're welcome to add features if time allows. Some natural additions: better input validation, proper logging, tests, or health checks per service. Just make sure the core bugs are fixed and the architecture is clean before adding new things.

---

### Can we use an ORM like SQLAlchemy?

Yes. You can use SQLAlchemy, Tortoise ORM, SQLModel, or any other library. Just add it to your `requirements.txt`. Using an ORM is a reasonable architectural improvement over the raw SQL strings in the monolith.

---

### How should we handle shared state between services?

The monolith uses global variables (`_user_sessions`, `_content_cache`, `_request_count`, etc.) for state management. In a microservices architecture, each service manages its own state. Options:
- Store sessions in the database or a cache (Redis, etc.)
- Make services stateless where possible (JWT tokens already carry user info)
- Have each service manage only the state it needs

Eliminating unnecessary global mutable state is part of the code quality evaluation.

---

### What's the deal with `mystery_table`?

Kevin created it "for something, I think analytics?" — it's dead code. It's never read or written to by any endpoint. You can safely ignore or remove it when extracting services.

---

### Can we use AI tools during the hackathon?

AI tools are permitted, but you may not paste the entire codebase and ask AI to refactor it for you. Every architectural decision must be understood and defendable by the team member who implemented it. During the demo, team members will be asked to explain their contributions and decisions.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'fastapi'`

Dependencies aren't installed. Run:
```bash
uv pip install -r requirements.txt
# or: pip install -r requirements.txt
```

### `GROQ_API_KEY not configured`

The app can't find your Groq API key. Make sure:
1. You copied `.env.example` to `.env`
2. You replaced `your-groq-api-key-here` with your actual key
3. If running with `python main.py`, you may need to load the `.env` file manually or export the variable:
   ```bash
   export GROQ_API_KEY=your-actual-key
   python main.py
   ```

### `Address already in use` (port 8000)

Another process is using port 8000. Either stop it or run on a different port:
```bash
uvicorn main:app --port 8001
```

### Chat endpoint returns 502 or 504

This usually means the Groq API is having issues or your API key is invalid. Check:
1. Your API key is correct
2. You have Groq API credits remaining
3. Try the request again — transient API errors happen

### SQLite `database is locked`

This can happen if multiple processes are accessing the same `aise_ask.db` file. Make sure only one instance of the app is running. Delete `aise_ask.db` to start fresh — it gets recreated on startup.

### Content upload says success but nothing appears

That's the bug. You're supposed to fix it. Read the upload endpoint code carefully.
