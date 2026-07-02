from dataclasses import dataclass, field
from typing import Protocol

from app.config import get_settings
from app.connectors.text import truncate
from app.models import Document
from app.supermemory.ingest import upload_documents

_MAX_SYNC_ERRORS = 50


@dataclass
class SyncResult:
    documents_processed: int = 0
    errors: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        if len(self.errors) < _MAX_SYNC_ERRORS:
            self.errors.append(message)

    def can_add_documents(self, count: int = 1) -> bool:
        settings = get_settings()
        return self.documents_processed + count <= settings.max_documents_per_sync

    def truncate(self, content: str) -> str:
        return truncate(content)


def upload_document_batch(documents: list[Document], result: SyncResult) -> None:
    if not documents:
        return
    settings = get_settings()
    remaining = settings.max_documents_per_sync - result.documents_processed
    if remaining <= 0:
        result.add_error("Max documents per sync reached")
        return
    batch = documents[:remaining]
    upload_documents(batch)
    result.documents_processed += len(batch)
    if len(documents) > len(batch):
        result.add_error(
            f"Truncated upload: {len(documents) - len(batch)} documents skipped (sync limit)"
        )


class Connector(Protocol):
    provider: str

    async def sync(self) -> SyncResult: ...

    def is_authenticated(self) -> bool: ...
