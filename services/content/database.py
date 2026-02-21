import sqlite3
import json
import uuid
import os

DATABASE_PATH = os.getenv("CONTENT_DB_PATH", "content.db")


def get_conn():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS content (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                content_type TEXT DEFAULT 'lesson',
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                uploaded_by TEXT,
                is_indexed INTEGER DEFAULT 1
            )
        """)
        conn.commit()

        # Seed default content if empty
        count = conn.execute("SELECT COUNT(*) FROM content").fetchone()[0]
        if count == 0:
            _seed_content(conn)
    finally:
        conn.close()
        
    print("[content-service] Database initialized.")


def _seed_content(conn):
    default_content = [
        {
            "id": str(uuid.uuid4()),
            "title": "Introduction to AI Safety",
            "body": "AI Safety is a field dedicated to ensuring that artificial intelligence systems are developed and deployed in ways that are safe, beneficial, and aligned with human values. Key topics include alignment, interpretability, robustness, and governance.",
            "content_type": "lesson",
            "metadata": json.dumps({"week": 1, "module": "foundations", "tags": ["ai-safety", "intro", "alignment"]}),
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Prompt Engineering Fundamentals",
            "body": "Prompt engineering is the practice of designing and refining inputs to large language models to achieve desired outputs. Techniques include zero-shot prompting, few-shot prompting, chain-of-thought reasoning, and system prompt design.",
            "content_type": "lesson",
            "metadata": json.dumps({"week": 2, "module": "prompt-engineering", "tags": ["prompts", "llm", "techniques"]}),
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Building AI Agents",
            "body": "AI Agents are systems that use LLMs as reasoning engines to take actions, use tools, and accomplish goals autonomously. Key concepts include tool use, planning, memory systems, and evaluation.",
            "content_type": "lesson",
            "metadata": json.dumps({"week": 5, "module": "agents", "tags": ["agents", "tools", "planning"]}),
        },
        {
            "id": str(uuid.uuid4()),
            "title": "AISE Program Schedule",
            "body": "Week 1-2: Foundations of AI Safety and Ethics. Week 3-4: Prompt Engineering and LLM APIs. Week 5-8: Building AI Agents and Tool Use. Week 9-10: Evaluation and Red Teaming. Week 11-12: Capstone Projects and Presentations.",
            "content_type": "schedule",
            "metadata": json.dumps({"type": "schedule", "version": "2025-fall"}),
        },
    ]
    for item in default_content:
        conn.execute(
            "INSERT INTO content (id, title, body, content_type, metadata, is_indexed) VALUES (?, ?, ?, ?, ?, 1)",
            (item["id"], item["title"], item["body"], item["content_type"], item["metadata"]),
        )
    conn.commit()
    print("[content-service] Seeded default content.")

_content_cache = None

def get_cached_content(force_refresh=False):
    """
    Retrieves indexed content from the database, caching the results in memory.
    Replaces the legacy 'it_works_dont_ask_why' function.
    """
    global _content_cache
    if _content_cache is None or force_refresh:
        conn = get_conn()
        try:
            cursor = conn.execute("SELECT id, title, body, content_type, metadata FROM content WHERE is_indexed = 1")
            rows = cursor.fetchall()
            
            new_cache = {}
            for row in rows:
                try:
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                except json.JSONDecodeError:
                    metadata = {}
                    
                new_cache[row["id"]] = {
                    "id": row["id"],
                    "title": row["title"],
                    "body": row["body"],
                    "content_type": row["content_type"],
                    "metadata": metadata,
                }
            _content_cache = new_cache
        finally:
            conn.close()
        
    return _content_cache
