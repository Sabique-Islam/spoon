import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

from app.auth.gdrive_oauth import has_service_account_fallback
from app.auth.store import get_provider_token
from app.config import get_settings
from app.connectors.base import SyncResult
from app.models import Document
from app.supermemory.ingest import upload_documents

logger = logging.getLogger("spoon")

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
PAGE_SIZE = 100
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

EXPORT_MIME_TYPES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

DOWNLOAD_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/xml",
    "text/html",
}

LIST_QUERY = (
    "trashed=false and "
    "mimeType!='application/vnd.google-apps.folder' and "
    "mimeType!='application/vnd.google-apps.shortcut'"
)
LIST_FIELDS = (
    "nextPageToken,files(id,name,mimeType,modifiedTime,createdTime,webViewLink,description)"
)


def file_to_document(file_meta: dict[str, Any], content: str) -> Document:
    settings = get_settings()
    file_id = file_meta["id"]
    name = file_meta.get("name") or "Untitled"

    content_parts = []
    if file_meta.get("description"):
        content_parts.append(file_meta["description"])
    content_parts.append(content)
    body = _truncate("\n\n".join(part for part in content_parts if part))

    details = [
        "Type: Google Drive file",
        f"Mime type: {file_meta.get('mimeType', 'unknown')}",
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
            "mime_type": file_meta.get("mimeType"),
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
                method, url, headers=headers, timeout=60.0, **kwargs
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

    async def _fetch_file_content(
        self,
        client: httpx.AsyncClient,
        token: str,
        file_meta: dict[str, Any],
    ) -> str | None:
        file_id = file_meta["id"]
        mime_type = file_meta.get("mimeType", "")

        if mime_type in EXPORT_MIME_TYPES:
            export_mime = EXPORT_MIME_TYPES[mime_type]
            response = await self._request(
                client,
                "GET",
                f"{DRIVE_API_BASE}/files/{file_id}/export",
                token,
                params={"mimeType": export_mime},
            )
        elif mime_type in DOWNLOAD_MIME_TYPES:
            response = await self._request(
                client,
                "GET",
                f"{DRIVE_API_BASE}/files/{file_id}",
                token,
                params={"alt": "media"},
            )
        else:
            return None

        if response.status_code in {403, 404}:
            return None
        response.raise_for_status()
        return response.text

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
                file_id = file_meta.get("id")
                if not file_id:
                    continue
                name = file_meta.get("name", file_id)
                try:
                    content = await self._fetch_file_content(client, token, file_meta)
                    if content is None:
                        continue
                    if not content.strip():
                        continue
                    documents.append(file_to_document(file_meta, content))
                except httpx.HTTPError as exc:
                    result.errors.append(f"Failed to fetch file {name}: {exc}")

            try:
                upload_documents(documents)
                result.documents_processed = len(documents)
            except Exception as exc:
                logger.exception("Supermemory upload failed")
                result.errors.append(f"Failed to upload documents: {exc}")

        return result
