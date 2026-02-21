"""Content Service — database helpers."""

import os
import json
import sqlite3
import uuid

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DATABASE_PATH = os.getenv("CONTENT_DB_PATH", os.path.join(os.path.dirname(__file__), "content.db"))


def get_conn():
    return sqlite3.connect(DATABASE_PATH)


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS content (
            id TEXT PRIMARY KEY,
            title TEXT,
            body TEXT,
            content_type TEXT DEFAULT 'lesson',
            metadata TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT,
            uploaded_by TEXT,
            is_indexed INTEGER DEFAULT 0
        )
    """)
    conn.commit()

    # Seed default content if empty
    c.execute("SELECT COUNT(*) FROM content")
    if c.fetchone()[0] == 0:
        defaults = [
            {
                "id": str(uuid.uuid4()),
                "title": "Introduction to AI Safety",
                "body": "AI Safety is a field dedicated to ensuring that artificial intelligence systems are developed and deployed in ways that are safe, beneficial, and aligned with human values. Key topics include alignment, interpretability, robustness, and governance. The AISE program covers these fundamentals across 12 weeks of intensive study.",
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
        for item in defaults:
            c.execute(
                "INSERT INTO content (id, title, body, content_type, metadata, is_indexed) VALUES (?, ?, ?, ?, ?, 1)",
                (item["id"], item["title"], item["body"], item["content_type"], item["metadata"]),
            )
        conn.commit()
    conn.close()
