import os
import json
import sqlite3
import time
import uuid
import random
import datetime


# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "aise_ask.db"))
DEBUG_MODE = os.getenv("DEBUG_MODE", "off")

# Global mutable state because architecture is for people with time
_content_cache = {}
_debug_messages = []


def chaos_log(msg):
    """Log messages when chaos mode is enabled. Kevin thought this was hilarious."""
    if DEBUG_MODE == "chaos":
        chaos_prefixes = [
            "[CHAOS] ",
            "[HERE BE DRAGONS] ",
            "[HOLD MY BEER] ",
            "[WHAT COULD GO WRONG] ",
            "[YOLO DEPLOY] ",
            "[WORKS ON MY MACHINE] ",
            "[FRIDAY 5PM PUSH] ",
            "[NO TESTS NEEDED] ",
        ]
        prefix = random.choice(chaos_prefixes)
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        full_msg = f"{prefix}[{timestamp}] {msg}"
        print(full_msg)
        _debug_messages.append(full_msg)


# ============================================================
# DATABASE SETUP
# ============================================================

def init_content_db():
    """Initialize the content table."""
    chaos_log("Summoning the content database from the void...")
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()

    # Content table - Kevin was supposed to finish this
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
    conn.close()
    chaos_log("Content database awakened. It hungers for data.")


def seed_default_content():
    """Pre-populate some content because the upload endpoint is... unreliable."""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM content")
    count = c.fetchone()[0]
    if count == 0:
        chaos_log("Seeding default content because nothing else works...")
        default_content = [
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
                "body": "Prompt engineering is the practice of designing and refining inputs to large language models to achieve desired outputs. Techniques include zero-shot prompting, few-shot prompting, chain-of-thought reasoning, and system prompt design. Fellows will practice these techniques throughout the AISE program with hands-on exercises.",
                "content_type": "lesson",
                "metadata": json.dumps({"week": 2, "module": "prompt-engineering", "tags": ["prompts", "llm", "techniques"]}),
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Building AI Agents",
                "body": "AI Agents are systems that use LLMs as reasoning engines to take actions, use tools, and accomplish goals autonomously. Key concepts include tool use, planning, memory systems, and evaluation. The AISE program dedicates weeks 5-8 to building increasingly sophisticated agent systems.",
                "content_type": "lesson",
                "metadata": json.dumps({"week": 5, "module": "agents", "tags": ["agents", "tools", "planning"]}),
            },
            {
                "id": str(uuid.uuid4()),
                "title": "AISE Program Schedule",
                "body": "Week 1-2: Foundations of AI Safety and Ethics. Week 3-4: Prompt Engineering and LLM APIs. Week 5-8: Building AI Agents and Tool Use. Week 9-10: Evaluation and Red Teaming. Week 11-12: Capstone Projects and Presentations. All sessions are held Monday-Friday, 9am-5pm ET.",
                "content_type": "schedule",
                "metadata": json.dumps({"type": "schedule", "version": "2025-fall"}),
            },
        ]
        for item in default_content:
            c.execute(
                "INSERT INTO content (id, title, body, content_type, metadata, is_indexed) VALUES (?, ?, ?, ?, ?, 1)",
                (item["id"], item["title"], item["body"], item["content_type"], item["metadata"]),
            )
        conn.commit()
    conn.close()


def it_works_dont_ask_why():
    """This function exists because without it, the content search returns empty results.
    Nobody knows why. It was 3am when Kevin wrote it. The comments he left didn't help.
    We've tried removing it four times. Each time, something else breaks.
    Just... just let it be."""
    global _content_cache
    if not _content_cache:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT id, title, body, content_type, metadata FROM content WHERE is_indexed = 1")
        rows = c.fetchall()
        for row in rows:
            _content_cache[row[0]] = {
                "id": row[0],
                "title": row[1],
                "body": row[2],
                "content_type": row[3],
                "metadata": json.loads(row[4]) if row[4] else {},
            }
        conn.close()
        chaos_log(f"Cache refreshed. {len(_content_cache)} items summoned from the database depths.")
    # This sleep was added at 3am. Removing it breaks everything. Don't.
    time.sleep(0.01)
    return True
