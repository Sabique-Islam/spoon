from app.config import get_settings
from app.models import Document
from app.supermemory.client import get_supermemory_client

BATCH_SIZE = 20


def _sanitize_custom_id(doc_id: str) -> str:
    sanitized = "".join(c if c.isalnum() or c in "-_." else "-" for c in doc_id)
    return sanitized[:100]


def _doc_to_payload(doc: Document) -> dict:
    settings = get_settings()
    metadata = {
        "source": doc.source,
        "title": doc.title,
        "url": doc.url,
    }
    for key, value in doc.metadata.items():
        if isinstance(value, (str, int, float, bool)):
            metadata[key] = value
        elif value is not None:
            metadata[key] = str(value)

    return {
        "content": doc.content,
        "custom_id": _sanitize_custom_id(doc.id),
        "metadata": metadata,
        "container_tag": settings.container_tag,
    }


def upload_document(doc: Document) -> None:
    client = get_supermemory_client()
    payload = _doc_to_payload(doc)
    client.documents.add(**payload)


def upload_documents(docs: list[Document]) -> None:
    if not docs:
        return

    client = get_supermemory_client()
    settings = get_settings()

    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i : i + BATCH_SIZE]
        documents = [_doc_to_payload(doc) for doc in batch]
        client.documents.batch_add(
            documents=documents,
            container_tag=settings.container_tag,
        )
