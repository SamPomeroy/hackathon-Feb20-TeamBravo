"""Chat Service — request/response models."""

from pydantic import BaseModel
from typing import Optional


class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None
