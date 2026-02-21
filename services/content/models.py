from typing import Optional
from pydantic import BaseModel


class ContentUpload(BaseModel):
    title: str
    body: str
    content_type: Optional[str] = "lesson"
    metadata: Optional[dict] = None


class ContentSearch(BaseModel):
    query: str
    limit: Optional[int] = 5
