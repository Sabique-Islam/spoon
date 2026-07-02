from typing import Any, Literal

from pydantic import BaseModel, Field


class Document(BaseModel):
    id: str
    source: Literal["notion", "linear", "gdrive"]
    title: str
    content: str
    url: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SyncResponse(BaseModel):
    provider: str
    documents_processed: int
    errors: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


class SearchResponse(BaseModel):
    results: Any


class ErrorResponse(BaseModel):
    error: str


class HealthResponse(BaseModel):
    status: str = "ok"


class ProvidersResponse(BaseModel):
    providers: list[str]
