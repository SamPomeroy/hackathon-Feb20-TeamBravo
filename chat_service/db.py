import sqlite3

DATABASE_PATH = "chat.db"

def get_connection():
    """Returns a sqlite3 connection."""
    return sqlite3.connect(DATABASE_PATH)

def init_db():
    """Create chat_history table if it doesn't exist."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            message TEXT NOT NULL,
            response TEXT NOT NULL,
            session_id TEXT NOT NULL,
            tokens_used INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()