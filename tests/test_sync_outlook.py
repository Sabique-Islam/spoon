from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_sync_outlook_success():
    list_response = MagicMock()
    list_response.status_code = 200
    list_response.json.return_value = {
        "value": [
            {
                "id": "msg-1",
                "subject": "Test email",
                "from": {"emailAddress": {"address": "alice@acme.com"}},
                "toRecipients": [{"emailAddress": {"address": "bob@acme.com"}}],
                "ccRecipients": [],
                "receivedDateTime": "2024-01-01T00:00:00Z",
                "body": {"contentType": "text", "content": "Hello Outlook"},
                "webLink": "https://outlook.office.com/mail/id/msg-1",
                "conversationId": "conv-1",
                "isDraft": False,
            }
        ]
    }
    list_response.raise_for_status = MagicMock()

    async def mock_request(method, url, **kwargs):
        if "/me/messages" in url:
            return list_response
        raise AssertionError(f"unexpected url {url}")

    mock_client = AsyncMock()
    mock_client.request = mock_request
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.connectors.outlook.get_provider_token", return_value={"access_token": "tok"}),
        patch("app.connectors.outlook.httpx.AsyncClient", return_value=mock_client),
        patch("app.connectors.base.upload_documents") as mock_upload,
        patch(
            "app.connectors.outlook.refresh_outlook_token_if_needed",
            new=AsyncMock(return_value="tok"),
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/sync/outlook")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "outlook"
    assert data["documents_processed"] == 1
    assert data["errors"] == []
    mock_upload.assert_called()


@pytest.mark.asyncio
async def test_sync_outlook_not_authenticated():
    with patch("app.connectors.outlook.get_provider_token", return_value=None):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/sync/outlook")

    assert response.status_code == 401
