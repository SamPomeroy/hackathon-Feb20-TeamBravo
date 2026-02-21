import json
import uuid
import os
from datetime import datetime, timezone
from collections import OrderedDict
from sqlalchemy import create_engine, Column, String, Integer, Text
from sqlalchemy.orm import sessionmaker, declarative_base, Session

DATABASE_PATH = os.getenv("CONTENT_DB_PATH", "content.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class DBContent(Base):
    __tablename__ = "content"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    content_type = Column(String, default="lesson")
    metadata_json = Column("metadata", Text, nullable=True)
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String, nullable=True)
    uploaded_by = Column(String, nullable=True)
    is_indexed = Column(Integer, default=1)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_session():
    """Returns a direct session, mostly used for synchronous non-request contexts like init_db"""
    return SessionLocal()

def init_db():
    Base.metadata.create_all(bind=engine)
    
    db = get_session()
    try:
        # Seed default content if count is 0
        count = db.query(DBContent).count()
        if count == 0:
            _seed_content(db)
    finally:
        db.close()
        
    print("[content-service] Database initialized.")


def _seed_content(db: Session):
    default_content = [
        {
            "id": str(uuid.uuid4()),
            "title": "Introduction to AI Safety",
            "body": "AI Safety is a field dedicated to ensuring that artificial intelligence systems are developed and deployed in ways that are safe, beneficial, and aligned with human values. Key topics include alignment, interpretability, robustness, and governance.",
            "content_type": "lesson",
            "metadata_json": json.dumps({"week": 1, "module": "foundations", "tags": ["ai-safety", "intro", "alignment"]}),
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Prompt Engineering Fundamentals",
            "body": "Prompt engineering is the practice of designing and refining inputs to large language models to achieve desired outputs. Techniques include zero-shot prompting, few-shot prompting, chain-of-thought reasoning, and system prompt design.",
            "content_type": "lesson",
            "metadata_json": json.dumps({"week": 2, "module": "prompt-engineering", "tags": ["prompts", "llm", "techniques"]}),
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Building AI Agents",
            "body": "AI Agents are systems that use LLMs as reasoning engines to take actions, use tools, and accomplish goals autonomously. Key concepts include tool use, planning, memory systems, and evaluation.",
            "content_type": "lesson",
            "metadata_json": json.dumps({"week": 5, "module": "agents", "tags": ["agents", "tools", "planning"]}),
        },
        {
            "id": str(uuid.uuid4()),
            "title": "AISE Program Schedule",
            "body": "Week 1-2: Foundations of AI Safety and Ethics. Week 3-4: Prompt Engineering and LLM APIs. Week 5-8: Building AI Agents and Tool Use. Week 9-10: Evaluation and Red Teaming. Week 11-12: Capstone Projects and Presentations.",
            "content_type": "schedule",
            "metadata_json": json.dumps({"type": "schedule", "version": "2025-fall"}),
        },
    ]
    for item in default_content:
        db.add(DBContent(**item, is_indexed=1))
    db.commit()
    print("[content-service] Seeded default content.")

MAX_CACHE_SIZE = 1000
_content_cache = None

def update_item_in_cache(item_dict: dict):
    """
    Updates or inserts a specific item into the memory cache using an LRU strategy.
    If the cache hasn't been initialized yet, it does nothing
    (the next read will pull the fresh state from the DB).
    """
    global _content_cache
    if _content_cache is not None:
        key = item_dict["id"]
        _content_cache[key] = item_dict
        _content_cache.move_to_end(key)
        
        # Evict oldest item if we exceed capacity
        if len(_content_cache) > MAX_CACHE_SIZE:
            _content_cache.popitem(last=False)

def get_cached_content(force_refresh=False):
    """
    Retrieves indexed content from the database, caching the results in memory.
    Implements an LRU cache bounded by MAX_CACHE_SIZE.
    """
    global _content_cache
    if _content_cache is None or force_refresh:
        db = get_session()
        try:
            # Query up to MAX_CACHE_SIZE newest items
            rows = db.query(DBContent).filter(DBContent.is_indexed == 1).order_by(DBContent.created_at.desc()).limit(MAX_CACHE_SIZE).all()
            
            new_cache = OrderedDict()
            # Iterate in reverse to insert oldest first, so newest are most recently used
            for row in reversed(rows):
                try:
                    metadata_dict = json.loads(row.metadata_json) if row.metadata_json else {}
                except json.JSONDecodeError:
                    metadata_dict = {}
                    
                new_cache[row.id] = {
                    "id": row.id,
                    "title": row.title,
                    "body": row.body,
                    "content_type": row.content_type,
                    "metadata": metadata_dict,
                }
            _content_cache = new_cache
        finally:
            db.close()
        
    return _content_cache
