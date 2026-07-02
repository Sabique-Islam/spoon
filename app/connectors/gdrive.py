import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

from app.auth.gdrive_oauth import GOOGLE_SCOPE_LIST, has_service_account_fallback
from app.auth.store import get_provider_token
from app.config import get_settings
from app.connectors.base import SyncResult
from app.connectors.gdrive_content import (
    export_formats_for,
    extract_text,
    is_google_app,
    should_skip_mime_type,
    supermemory_file_type,
)
from app.models import Document
from app.supermemory.ingest import upload_document, upload_documents, upload_file_document

logger = logging.getLogger("spoon")

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
PAGE_SIZE = 100
DRIVE_SCOPES = GOOGLE_SCOPE_LIST

LIST_QUERY = (
    "trashed=false and "
    "mimeType!='application/vnd.google-apps.folder' and "
    "mimeType!='application/vnd.google-apps.shortcut'"
)
LIST_FIELDS = (
    "nextPageToken,files(id,name,mimeType,modifiedTime,createdTime,webViewLink,description)"
)


def file_to_document(file_meta: dict[str, Any], content: str) -> Document:
    file_id = file_meta["id"]
    name = file_meta.get("name") or "Untitled"
    mime_type = file_meta.get("mimeType", "application/octet-stream")

    content_parts = []
    if file_meta.get("description"):
        content_parts.append(file_meta["description"])
    content_parts.append(content)
    body = _truncate("\n\n".join(part for part in content_parts if part))

    details = [
        "Type: Google Drive file",
        f"Mime type: {mime_type}",
    ]
    if file_meta.get("createdTime"):
        details.append(f"Created: {file_meta['createdTime']}")
    if file_meta.get("modifiedTime"):
        details.append(f"Modified: {file_meta['modifiedTime']}")

    full_content = _truncate(f"{body}\n\n" + "\n".join(details))

    return Document(
        id=f"gdrive-{file_id}",
        source="gdrive",
        title=name,
        content=full_content.strip(),
        url=file_meta.get("webViewLink")
        or f"https://drive.google.com/file/d/{file_id}/view",
        metadata={
            "object_type": "file",
            "file_id": file_id,
            "filename": name,
            "mime_type": mime_type,
            "created_time": file_meta.get("createdTime"),
            "modified_time": file_meta.get("modifiedTime"),
        },
    )


def _truncate(content: str) -> str:
    return content[: get_settings().max_content_length]


def _service_account_token() -> str | None:
    settings = get_settings()
    if not settings.gdrive_api_key:
        return None

    path = Path(settings.gdrive_api_key)
    if not path.is_file():
        return None

    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except ImportError:
        logger.error(
            "google-auth and requests are required for service account fallback. "
            "Run: pip install google-auth requests"
        )
        return None

    credentials = service_account.Credentials.from_service_account_file(
        str(path),
        scopes=DRIVE_SCOPES,
    )
    credentials.refresh(Request())
    return credentials.token


class GDriveConnector:
    provider = "gdrive"

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

        token = _service_account_token()
        if token:
            return token

        raise ValueError(
            "Google Drive is not authenticated. Visit /api/v1/auth/gdrive or set SPOON_GDRIVE_API_KEY to a service account JSON path."
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

    async def _fetch_files(
        self, client: httpx.AsyncClient, token: str
    ) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {
                "q": LIST_QUERY,
                "pageSize": PAGE_SIZE,
                "fields": LIST_FIELDS,
            }
            if page_token:
                params["pageToken"] = page_token

            response = await self._request(
                client,
                "GET",
                f"{DRIVE_API_BASE}/files",
                token,
                params=params,
            )
            if response.status_code == 401:
                raise httpx.HTTPStatusError(
                    "Unauthorized", request=response.request, response=response
                )
            response.raise_for_status()
            data = response.json()
            files.extend(data.get("files", []))

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return files

    async def _download_export(
        self,
        client: httpx.AsyncClient,
        token: str,
        file_id: str,
        export_mime: str,
    ) -> httpx.Response:
        return await self._request(
            client,
            "GET",
            f"{DRIVE_API_BASE}/files/{file_id}/export",
            token,
            params={"mimeType": export_mime},
        )

    async def _download_media(
        self,
        client: httpx.AsyncClient,
        token: str,
        file_id: str,
    ) -> httpx.Response:
        return await self._request(
            client,
            "GET",
            f"{DRIVE_API_BASE}/files/{file_id}",
            token,
            params={"alt": "media"},
        )

    async def _fetch_file_bytes(
        self,
        client: httpx.AsyncClient,
        token: str,
        file_meta: dict[str, Any],
    ) -> tuple[bytes, str] | None:
        file_id = file_meta["id"]
        mime_type = file_meta.get("mimeType", "application/octet-stream")

        if should_skip_mime_type(mime_type):
            return None

        if is_google_app(mime_type):
            for export_mime in export_formats_for(mime_type):
                response = await self._download_export(
                    client, token, file_id, export_mime
                )
                if response.status_code in {403, 404}:
                    continue
                if response.status_code >= 400:
                    response.raise_for_status()
                if response.content:
                    return response.content, export_mime
            return None

        response = await self._download_media(client, token, file_id)
        if response.status_code in {403, 404}:
            return None
        response.raise_for_status()
        if not response.content:
            return None
        return response.content, mime_type

    async def _process_file(
        self,
        client: httpx.AsyncClient,
        token: str,
        file_meta: dict[str, Any],
    ) -> bool:
        name = file_meta.get("name", file_meta.get("id", "file"))
        mime_type = file_meta.get("mimeType", "application/octet-stream")

        fetched = await self._fetch_file_bytes(client, token, file_meta)
        if not fetched:
            return False

        data, effective_mime = fetched
        text = extract_text(name, effective_mime, data)
        doc = file_to_document(file_meta, text or name)

        if text and text.strip():
            upload_document(doc)
            return True

        upload_file_document(
            doc,
            data,
            effective_mime,
            name,
            file_type=supermemory_file_type(mime_type, name)
            or supermemory_file_type(effective_mime, name),
        )
        return True

    async def sync(self) -> SyncResult:
        result = SyncResult()

        try:
            token = await self._resolve_token()
        except ValueError as exc:
            result.errors.append(str(exc))
            return result

        processed = 0

        async with httpx.AsyncClient() as client:
            try:
                files = await self._fetch_files(client, token)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    from app.auth.gdrive_oauth import refresh_gdrive_token_if_needed

                    refreshed = await refresh_gdrive_token_if_needed()
                    if refreshed:
                        try:
                            files = await self._fetch_files(client, refreshed)
                            token = refreshed
                        except httpx.HTTPError as retry_exc:
                            result.errors.append(
                                f"Failed to fetch Google Drive files: {retry_exc}"
                            )
                            return result
                    else:
                        result.errors.append(
                            "Google Drive token expired. Re-authenticate at /api/v1/auth/gdrive."
                        )
                        return result
                else:
                    result.errors.append(f"Failed to fetch Google Drive files: {exc}")
                    return result
            except httpx.HTTPError as exc:
                result.errors.append(f"Failed to fetch Google Drive files: {exc}")
                return result

            for file_meta in files:
                if not file_meta.get("id"):
                    continue
                name = file_meta.get("name", file_meta["id"])
                try:
                    if await self._process_file(client, token, file_meta):
                        processed += 1
                except httpx.HTTPError as exc:
                    result.errors.append(f"Failed to process file {name}: {exc}")
                except Exception as exc:
                    logger.exception("Failed to process Drive file %s", name)
                    result.errors.append(f"Failed to process file {name}: {exc}")

            result.documents_processed = processed

        return result
