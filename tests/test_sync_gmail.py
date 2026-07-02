import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_sync_gmail_success():
    list_response = MagicMock()
    list_response.status_code = 200
    list_response.json.return_value = {
        "messages": [{"id": "msg-1", "threadId": "thread-1"}]
    }
    list_response.raise_for_status = MagicMock()

    body_data = base64.urlsafe_b64encode(b"Hello from Gmail").decode()
    message_response = MagicMock()
    message_response.status_code = 200
    message_response.json.return_value = {
        "id": "msg-1",
        "threadId": "thread-1",
        "snippet": "Hello from Gmail",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Test email"},
                {"name": "From", "value": "alice@acme.com"},
                {"name": "To", "value": "bob@acme.com"},
            ],
            "mimeType": "text/plain",
            "body": {"data": body_data},
        },
    }
    message_response.raise_for_status = MagicMock()

    async def mock_request(method, url, **kwargs):
        if url.endswith("/users/me/messages") and "msg-1" not in url:
            return list_response
        if url.endswith("/users/me/messages/msg-1"):
            return message_response
        raise AssertionError(f"unexpected url {url}")

    mock_client = AsyncMock()
    mock_client.request = mock_request
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.connectors.gmail.get_provider_token", return_value={"access_token": "tok"}),
        patch("app.connectors.gmail.httpx.AsyncClient", return_value=mock_client),
        patch("app.connectors.base.upload_documents") as mock_upload,
        patch(
            "app.auth.gdrive_oauth.refresh_gdrive_token_if_needed",
            return_value="tok",
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/sync/gmail")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "gmail"
    assert data["documents_processed"] == 1
    assert data["errors"] == []
    mock_upload.assert_called_once()


@pytest.mark.asyncio
async def test_sync_gmail_not_authenticated():
    with (
        patch("app.connectors.gmail.get_provider_token", return_value=None),
        patch("app.connectors.gmail.has_service_account_fallback", return_value=False),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/sync/gmail")

    assert response.status_code == 401
