import asyncio
import logging
import re
from html import unescape
from typing import Any

import httpx

from app.auth.outlook_oauth import refresh_outlook_token_if_needed
from app.auth.store import get_provider_token
from app.config import get_settings
from app.connectors.base import SyncResult
from app.models import Document
from app.supermemory.ingest import upload_documents

logger = logging.getLogger("spoon")

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
PAGE_SIZE = 100
MESSAGE_SELECT = (
    "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,bodyPreview,"
    "webLink,conversationId,isDraft"
)
MESSAGE_FILTER = "isDraft eq false"


def _truncate(content: str) -> str:
    return content[: get_settings().max_content_length]


def _html_to_text(html: str) -> str:
    without_scripts = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", without_scripts)
    return unescape(re.sub(r"\s+", " ", text)).strip()


def _format_address(address: dict[str, Any] | None) -> str:
    if not address:
        return ""
    name = address.get("name", "").strip()
    email = address.get("address", "").strip()
    if name and email:
        return f"{name} <{email}>"
    return name or email


def _format_recipients(recipients: list[dict[str, Any]] | None) -> str:
    if not recipients:
        return ""
    return ", ".join(
        part
        for part in (_format_address(item.get("emailAddress")) for item in recipients)
        if part
    )


def _message_body(message: dict[str, Any]) -> str:
    body = message.get("body") or {}
    content = (body.get("content") or "").strip()
    if not content:
        return (message.get("bodyPreview") or "").strip()

    if (body.get("contentType") or "").lower() == "html":
        return _html_to_text(content)
    return content


def message_to_document(message: dict[str, Any]) -> Document | None:
    message_id = message.get("id")
    if not message_id or message.get("isDraft"):
        return None

    subject = (message.get("subject") or "").strip() or "(no subject)"
    sender = _format_address((message.get("from") or {}).get("emailAddress"))
    recipients = _format_recipients(message.get("toRecipients"))
    cc = _format_recipients(message.get("ccRecipients"))
    received = message.get("receivedDateTime") or ""
    body = _message_body(message)
    if not body:
        return None

    lines = [
        f"From: {sender}",
        f"To: {recipients}",
    ]
    if cc:
        lines.append(f"Cc: {cc}")
    if received:
        lines.append(f"Date: {received}")
    lines.append("")
    lines.append(body)

    content = _truncate("\n".join(lines))
    url = message.get("webLink") or "https://outlook.office.com/mail/"

    return Document(
        id=f"outlook-{message_id}",
        source="outlook",
        title=subject,
        content=content,
        url=url,
        metadata={
            "object_type": "email",
            "message_id": message_id,
            "conversation_id": message.get("conversationId"),
            "from": sender,
            "to": recipients,
            "date": received,
        },
    )


class OutlookConnector:
    provider = "outlook"

    def is_authenticated(self) -> bool:
        stored = get_provider_token("outlook")
        return bool(stored and stored.get("access_token"))

    async def _resolve_token(self) -> str:
        token = await refresh_outlook_token_if_needed()
        if not token:
            raise ValueError(
                "Outlook is not authenticated. Visit /api/v1/auth/outlook."
            )
        return token

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        token: str,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"

        last_response: httpx.Response | None = None
        for attempt in range(MAX_RETRIES):
            response = await client.request(
                method, url, headers=headers, timeout=120.0, **kwargs
            )
            last_response = response
            if response.status_code not in RETRYABLE_STATUS:
                return response

            retry_after = int(response.headers.get("Retry-After", 2**attempt))
            await asyncio.sleep(retry_after)

        assert last_response is not None
        return last_response

    async def _fetch_messages(
        self, client: httpx.AsyncClient, token: str
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        url: str | None = f"{GRAPH_API_BASE}/me/messages"
        params: dict[str, Any] | None = {
            "$top": PAGE_SIZE,
            "$select": MESSAGE_SELECT,
            "$filter": MESSAGE_FILTER,
            "$orderby": "receivedDateTime desc",
        }

        while url:
            response = await self._request(
                client,
                "GET",
                url,
                token,
                params=params if params else None,
            )
            if response.status_code == 401:
                raise httpx.HTTPStatusError(
                    "Unauthorized", request=response.request, response=response
                )
            response.raise_for_status()
            data = response.json()
            messages.extend(data.get("value") or [])
            url = data.get("@odata.nextLink")
            params = None

        return messages

    async def sync(self) -> SyncResult:
        result = SyncResult()

        try:
            token = await self._resolve_token()
        except ValueError as exc:
            result.errors.append(str(exc))
            return result

        documents: list[Document] = []

        async with httpx.AsyncClient() as client:
            try:
                messages = await self._fetch_messages(client, token)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    refreshed = await refresh_outlook_token_if_needed()
                    if refreshed and refreshed != token:
                        try:
                            messages = await self._fetch_messages(client, refreshed)
                            token = refreshed
                        except httpx.HTTPError as retry_exc:
                            result.errors.append(
                                f"Failed to fetch Outlook messages: {retry_exc}"
                            )
                            return result
                    else:
                        result.errors.append(
                            "Outlook token expired. Re-authenticate at /api/v1/auth/outlook."
                        )
                        return result
                else:
                    result.errors.append(f"Failed to fetch Outlook messages: {exc}")
                    return result
            except httpx.HTTPError as exc:
                result.errors.append(f"Failed to fetch Outlook messages: {exc}")
                return result

            for message in messages:
                message_id = message.get("id", "unknown")
                try:
                    doc = message_to_document(message)
                    if doc:
                        documents.append(doc)
                except Exception as exc:
                    logger.exception("Failed to process Outlook message %s", message_id)
                    result.errors.append(
                        f"Failed to process message {message_id}: {exc}"
                    )

            try:
                upload_documents(documents)
                result.documents_processed = len(documents)
            except Exception as exc:
                logger.exception("Supermemory upload failed")
                result.errors.append(f"Failed to upload documents: {exc}")

        return result
