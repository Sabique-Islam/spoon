from typing import Any

from app.config import get_settings
from app.supermemory.client import get_supermemory_client


def search_documents(query: str, limit: int = 10) -> Any:
    client = get_supermemory_client()
    settings = get_settings()
    response = client.search.documents(
        q=query,
        container_tags=[settings.container_tag],
        limit=limit,
    )
    return response.results
