from dataclasses import dataclass, field
from typing import Protocol

from app.models import Document


@dataclass
class SyncResult:
    documents_processed: int = 0
    errors: list[str] = field(default_factory=list)


class Connector(Protocol):
    provider: str

    async def sync(self) -> SyncResult: ...

    def is_authenticated(self) -> bool: ...
