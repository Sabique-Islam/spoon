import asyncio
import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.auth.gdrive_oauth import refresh_gdrive_token_if_needed
from app.auth.google_service_account import (
    has_service_account_fallback,
    service_account_token,
)
from app.auth.store import get_provider_token
from app.config import get_settings
from app.connectors.base import SyncResult, upload_document_batch
from app.connectors.text import html_to_text, truncate
from app.models import Document

logger = logging.getLogger("spoon")

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
PAGE_SIZE = 100
LIST_QUERY = "in:anywhere -in:spam -in:trash"


def _list_query() -> str:
    settings = get_settings()
    query = LIST_QUERY
    if settings.sync_since_days:
        since = datetime.now(timezone.utc) - timedelta(days=settings.sync_since_days)
        query = f"{query} after:{since.strftime('%Y/%m/%d')}"
    return query


def _truncate(content: str) -> str:
    return truncate(content)


def _decode_body(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _html_to_text(html: str) -> str:
    return html_to_text(html)


def _get_header(headers: list[dict[str, str]], name: str) -> str:
    target = name.lower()
    for header in headers:
        if header.get("name", "").lower() == target:
            return header.get("value", "")
    return ""


def _extract_body(payload: dict[str, Any]) -> tuple[str, str]:
    mime_type = payload.get("mimeType", "")
    body = payload.get("body") or {}
    data = body.get("data")

    if data:
        decoded = _decode_body(data)
        if mime_type == "text/plain":
            return decoded, ""
        if mime_type == "text/html":
            return "", decoded

    plain_parts: list[str] = []
    html_parts: list[str] = []
    for part in payload.get("parts") or []:
        plain, html = _extract_body(part)
        if plain:
            plain_parts.append(plain)
        if html:
            html_parts.append(html)

    return "\n".join(plain_parts), "\n".join(html_parts)


def message_to_document(message: dict[str, Any]) -> Document | None:
    message_id = message.get("id")
    if not message_id:
        return None

    payload = message.get("payload") or {}
    headers = payload.get("headers") or []
    subject = _get_header(headers, "Subject") or "(no subject)"
    sender = _get_header(headers, "From")
    recipients = _get_header(headers, "To")
    cc = _get_header(headers, "Cc")
    date = _get_header(headers, "Date")

    plain, html = _extract_body(payload)
    body = plain.strip() or _html_to_text(html) or (message.get("snippet") or "").strip()
    if not body:
        return None

    lines = [
        f"From: {sender}",
        f"To: {recipients}",
    ]
    if cc:
        lines.append(f"Cc: {cc}")
    if date:
        lines.append(f"Date: {date}")
    lines.append("")
    lines.append(body)

    label_ids = message.get("labelIds") or []
    content = _truncate("\n".join(lines))

    return Document(
        id=f"gmail-{message_id}",
        source="gmail",
        title=subject,
        content=content,
        url=f"https://mail.google.com/mail/u/0/#inbox/{message_id}",
        metadata={
            "object_type": "email",
            "message_id": message_id,
            "thread_id": message.get("threadId"),
            "from": sender,
            "to": recipients,
            "date": date,
            "label_ids": label_ids,
        },
    )


class GmailConnector:
    provider = "gmail"

    def is_authenticated(self) -> bool:
        stored = get_provider_token("gdrive")
        if stored and stored.get("access_token"):
            return True
        return has_service_account_fallback()

    async def _resolve_token(self) -> str:
        from app.auth.gdrive_oauth import refresh_gdrive_token_if_needed

        token = await refresh_gdrive_token_if_needed()
        if token:
            return token

        token = service_account_token()
        if token:
            return token

        raise ValueError(
            "Gmail is not authenticated. Visit /api/v1/auth/gdrive or set SPOON_GDRIVE_SERVICE_ACCOUNT_PATH."
        )

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
            await asyncio.sleep(2**attempt)

        assert last_response is not None
        return last_response

    async def _fetch_message_ids(
        self, client: httpx.AsyncClient, token: str
    ) -> list[str]:
        message_ids: list[str] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {
                "maxResults": PAGE_SIZE,
                "q": _list_query(),
            }
            if page_token:
                params["pageToken"] = page_token

            response = await self._request(
                client,
                "GET",
                f"{GMAIL_API_BASE}/users/me/messages",
                token,
                params=params,
            )
            if response.status_code == 401:
                raise httpx.HTTPStatusError(
                    "Unauthorized", request=response.request, response=response
                )
            response.raise_for_status()
            data = response.json()

            for item in data.get("messages") or []:
                message_id = item.get("id")
                if message_id:
                    message_ids.append(message_id)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return message_ids

    async def _fetch_message(
        self,
        client: httpx.AsyncClient,
        token: str,
        message_id: str,
    ) -> dict[str, Any]:
        response = await self._request(
            client,
            "GET",
            f"{GMAIL_API_BASE}/users/me/messages/{message_id}",
            token,
            params={"format": "full"},
        )
        if response.status_code in {403, 404}:
            raise httpx.HTTPStatusError(
                "Not found", request=response.request, response=response
            )
        response.raise_for_status()
        return response.json()

    async def sync(self) -> SyncResult:
        result = SyncResult()

        try:
            token = await self._resolve_token()
        except ValueError as exc:
            result.add_error(str(exc))
            return result

        async with httpx.AsyncClient() as client:
            try:
                message_ids = await self._fetch_message_ids(client, token)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    refreshed = await refresh_gdrive_token_if_needed()
                    if refreshed:
                        try:
                            message_ids = await self._fetch_message_ids(
                                client, refreshed
                            )
                            token = refreshed
                        except httpx.HTTPError as retry_exc:
                            result.add_error(
                                f"Failed to fetch Gmail messages: {retry_exc}"
                            )
                            return result
                    else:
                        result.add_error(
                            "Google token expired or missing Gmail scope. Re-authenticate at /api/v1/auth/gdrive."
                        )
                        return result
                else:
                    result.add_error(f"Failed to fetch Gmail messages: {exc}")
                    return result
            except httpx.HTTPError as exc:
                result.add_error(f"Failed to fetch Gmail messages: {exc}")
                return result

            settings = get_settings()
            if settings.max_documents_per_sync:
                message_ids = message_ids[: settings.max_documents_per_sync]

            for message_id in message_ids:
                if not result.can_add_documents():
                    break
                try:
                    message = await self._fetch_message(client, token, message_id)
                    doc = message_to_document(message)
                    if doc:
                        upload_document_batch([doc], result)
                except httpx.HTTPError as exc:
                    result.add_error(f"Failed to fetch message {message_id}: {exc}")
                except Exception as exc:
                    logger.exception("Failed to process Gmail message %s", message_id)
                    result.add_error(f"Failed to process message {message_id}: {exc}")

        return result
