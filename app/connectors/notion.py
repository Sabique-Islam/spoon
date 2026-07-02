import asyncio
import logging
from typing import Any

import httpx

from app.auth.oauth import get_notion_access_token, refresh_notion_token_if_needed
from app.config import get_settings
from app.connectors.base import SyncResult
from app.models import Document
from app.supermemory.ingest import upload_documents

logger = logging.getLogger("spoon")

NOTION_API_BASE = "https://api.notion.com/v1"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3


def extract_title(page: dict[str, Any]) -> str:
    properties = page.get("properties", {})
    for prop in properties.values():
        if prop.get("type") == "title":
            title_parts = prop.get("title", [])
            return "".join(part.get("plain_text", "") for part in title_parts).strip()
    return "Untitled"


def rich_text_to_plain(rich_text: list[dict[str, Any]]) -> str:
    return "".join(part.get("plain_text", "") for part in rich_text)


def block_to_text(block: dict[str, Any]) -> str:
    block_type = block.get("type", "")
    data = block.get(block_type, {})
    if not isinstance(data, dict):
        return ""

    if block_type in {
        "paragraph",
        "heading_1",
        "heading_2",
        "heading_3",
        "bulleted_list_item",
        "numbered_list_item",
        "to_do",
        "quote",
        "callout",
        "toggle",
    }:
        return rich_text_to_plain(data.get("rich_text", []))

    if block_type == "code":
        return rich_text_to_plain(data.get("rich_text", []))

    return ""


def blocks_to_plain_text(blocks: list[dict[str, Any]], depth: int = 0) -> str:
    settings = get_settings()
    if depth > settings.max_block_depth:
        return ""

    lines: list[str] = []
    for block in blocks:
        text = block_to_text(block)
        if text:
            lines.append(text)
        children = block.get("children", [])
        if children:
            child_text = blocks_to_plain_text(children, depth + 1)
            if child_text:
                lines.append(child_text)

    return "\n".join(lines)


def page_to_document(page: dict[str, Any], content: str) -> Document:
    page_id = page["id"]
    settings = get_settings()
    content = content[: settings.max_content_length]

    return Document(
        id=f"notion-{page_id}",
        source="notion",
        title=extract_title(page),
        content=content,
        url=f"https://www.notion.so/{page_id.replace('-', '')}",
        metadata={
            "page_id": page_id,
            "last_edited_time": page.get("last_edited_time"),
            "created_time": page.get("created_time"),
            "object_type": page.get("object"),
        },
    )


class NotionConnector:
    provider = "notion"

    def __init__(self) -> None:
        self._settings = get_settings()

    def is_authenticated(self) -> bool:
        from app.auth.store import get_provider_token

        settings = get_settings()
        if get_provider_token("notion"):
            return True
        return bool(settings.notion_api_key)

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        token: str,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": self._settings.notion_version,
            "Content-Type": "application/json",
        }

        last_response: httpx.Response | None = None
        for attempt in range(MAX_RETRIES):
            response = await client.request(
                method,
                f"{NOTION_API_BASE}{path}",
                headers=headers,
                timeout=30.0,
                **kwargs,
            )
            last_response = response
            if response.status_code not in RETRYABLE_STATUS:
                return response
            await asyncio.sleep(2**attempt)

        assert last_response is not None
        return last_response

    async def _fetch_block_children(
        self,
        client: httpx.AsyncClient,
        block_id: str,
        token: str,
        depth: int = 0,
    ) -> list[dict[str, Any]]:
        if depth > self._settings.max_block_depth:
            return []

        blocks: list[dict[str, Any]] = []
        start_cursor: str | None = None

        while True:
            params: dict[str, Any] = {"page_size": 100}
            if start_cursor:
                params["start_cursor"] = start_cursor

            response = await self._request(
                client, "GET", f"/blocks/{block_id}/children", token, params=params
            )
            if response.status_code == 401:
                raise httpx.HTTPStatusError(
                    "Unauthorized", request=response.request, response=response
                )
            response.raise_for_status()
            data = response.json()

            for block in data.get("results", []):
                if block.get("has_children"):
                    block["children"] = await self._fetch_block_children(
                        client, block["id"], token, depth + 1
                    )
                blocks.append(block)

            if not data.get("has_more"):
                break
            start_cursor = data.get("next_cursor")

        return blocks

    async def _fetch_pages(
        self, client: httpx.AsyncClient, token: str
    ) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        start_cursor: str | None = None

        while True:
            payload: dict[str, Any] = {
                "page_size": 100,
                "filter": {"property": "object", "value": "page"},
            }
            if start_cursor:
                payload["start_cursor"] = start_cursor

            response = await self._request(
                client, "POST", "/search", token, json=payload
            )
            if response.status_code == 401:
                raise httpx.HTTPStatusError(
                    "Unauthorized", request=response.request, response=response
                )
            response.raise_for_status()
            data = response.json()
            pages.extend(data.get("results", []))

            if not data.get("has_more"):
                break
            start_cursor = data.get("next_cursor")

        return pages

    async def _resolve_token(self) -> str:
        token = await get_notion_access_token()
        if not token:
            raise ValueError(
                "Notion is not authenticated. Visit /api/v1/auth/notion or set SPOON_NOTION_API_KEY."
            )
        return token

    async def sync(self) -> SyncResult:
        result = SyncResult()
        try:
            token = await self._resolve_token()
        except ValueError as exc:
            result.errors.append(str(exc))
            return result

        async with httpx.AsyncClient() as client:
            try:
                pages = await self._fetch_pages(client, token)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    token = await refresh_notion_token_if_needed()
                    if not token:
                        result.errors.append(
                            "Notion token expired. Re-authenticate at /api/v1/auth/notion."
                        )
                        return result
                    try:
                        pages = await self._fetch_pages(client, token)
                    except httpx.HTTPError as retry_exc:
                        result.errors.append(f"Failed to fetch Notion pages: {retry_exc}")
                        return result
                else:
                    result.errors.append(f"Failed to fetch Notion pages: {exc}")
                    return result
            except httpx.HTTPError as exc:
                result.errors.append(f"Failed to fetch Notion pages: {exc}")
                return result

            documents: list[Document] = []
            for page in pages:
                page_id = page.get("id")
                if not page_id:
                    continue
                try:
                    blocks = await self._fetch_block_children(client, page_id, token)
                    content = blocks_to_plain_text(blocks)
                    documents.append(page_to_document(page, content))
                except httpx.HTTPError as exc:
                    result.errors.append(f"Failed to fetch page {page_id}: {exc}")

            try:
                upload_documents(documents)
                result.documents_processed = len(documents)
            except Exception as exc:
                logger.exception("Supermemory upload failed")
                result.errors.append(f"Failed to upload documents: {exc}")

        return result
