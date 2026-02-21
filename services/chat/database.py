"""Chat Service — database helpers."""

import os
import sqlite3

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DATABASE_PATH = os.getenv("CHAT_DB_PATH", os.path.join(os.path.dirname(__file__), "chat.db"))


def get_conn():
    return sqlite3.connect(DATABASE_PATH)


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            message TEXT,
            response TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            session_id TEXT,
            tokens_used INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()
