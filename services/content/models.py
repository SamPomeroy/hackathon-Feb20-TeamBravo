from typing import Optional, List, Any
from pydantic import BaseModel


class ContentUpload(BaseModel):
    title: str
    body: str
    content_type: Optional[str] = "lesson"
    metadata: Optional[dict] = None


class ContentSearch(BaseModel):
    query: str
    limit: Optional[int] = 5


class UploadResponse(BaseModel):
    message: str
    content_id: str
    title: str
    status: str


class UploadFileResponse(BaseModel):
    message: str
    count: int
    content_ids: List[str]
    status: str


class SearchResultItem(BaseModel):
    id: str
    title: Optional[str] = None
    body: Optional[str] = None
    content_type: Optional[str] = None
    score: int
    metadata: Optional[dict] = None


class SearchResponse(BaseModel):
    results: List[SearchResultItem]
    total: int
    query: str
    source: str


class ContentItem(BaseModel):
    id: str
    title: Optional[str] = None
    body: Optional[str] = None
    content_type: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: Optional[str] = None


class ListContentResponse(BaseModel):
    content: List[ContentItem]
    total: int


class InternalContentItem(BaseModel):
    id: str
    title: Optional[str] = None
    body: Optional[str] = None
    content_type: Optional[str] = None


class ListInternalContentResponse(BaseModel):
    content: List[InternalContentItem]


class HealthResponse(BaseModel):
    status: str
    service: str
