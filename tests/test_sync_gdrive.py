from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_sync_gdrive_success():
    list_response = MagicMock()
    list_response.status_code = 200
    list_response.json.return_value = {
        "files": [
            {
                "id": "file-1",
                "name": "readme.txt",
                "mimeType": "text/plain",
                "webViewLink": "https://drive.google.com/file/d/file-1/view",
                "createdTime": "2024-01-01T00:00:00.000Z",
                "modifiedTime": "2024-01-02T00:00:00.000Z",
            }
        ]
    }
    list_response.raise_for_status = MagicMock()

    content_response = MagicMock()
    content_response.status_code = 200
    content_response.content = b"Drive file contents"
    content_response.text = "Drive file contents"
    content_response.raise_for_status = MagicMock()

    async def mock_request(method, url, **kwargs):
        if "/export" in url or kwargs.get("params", {}).get("alt") == "media":
            return content_response
        return list_response

    mock_client = AsyncMock()
    mock_client.request = mock_request
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.connectors.gdrive.get_provider_token", return_value={"access_token": "tok"}),
        patch("app.connectors.gdrive.httpx.AsyncClient", return_value=mock_client),
        patch("app.connectors.gdrive.upload_document") as mock_upload,
        patch("app.connectors.gdrive.get_settings") as mock_settings,
        patch(
            "app.auth.gdrive_oauth.refresh_gdrive_token_if_needed",
            return_value="tok",
        ),
    ):
        settings = MagicMock()
        settings.max_content_length = 100_000
        settings.max_file_bytes = 25_000_000
        settings.max_documents_per_sync = 5000
        mock_settings.return_value = settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/sync/gdrive")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "gdrive"
    assert data["documents_processed"] == 1
    assert data["errors"] == []
    mock_upload.assert_called_once()


@pytest.mark.asyncio
async def test_sync_gdrive_not_authenticated():
    with (
        patch("app.connectors.gdrive.get_provider_token", return_value=None),
        patch("app.connectors.gdrive.has_service_account_fallback", return_value=False),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/sync/gdrive")

    assert response.status_code == 401
