from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


SAMPLE_ISSUE = {
    "id": "issue-1",
    "identifier": "ENG-1",
    "title": "Test issue",
    "description": "Issue body",
    "url": "https://linear.app/acme/issue/ENG-1",
    "priority": 3,
    "createdAt": "2024-01-01T00:00:00.000Z",
    "updatedAt": "2024-01-02T00:00:00.000Z",
    "state": {"name": "Todo"},
    "team": {"name": "Engineering", "key": "ENG"},
    "assignee": None,
    "labels": {"nodes": []},
}


@pytest.mark.asyncio
async def test_sync_linear_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "issues": {
                "nodes": [SAMPLE_ISSUE],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            },
            "projects": {
                "nodes": [],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            },
        }
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.connectors.linear.httpx.AsyncClient", return_value=mock_client),
        patch("app.connectors.linear.upload_documents") as mock_upload,
        patch("app.connectors.linear.get_settings") as mock_settings,
    ):
        settings = MagicMock()
        settings.linear_api_key = "lin_api_test"
        settings.max_content_length = 100_000
        mock_settings.return_value = settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/sync/linear")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "linear"
    assert data["documents_processed"] == 1
    assert data["errors"] == []
    mock_upload.assert_called_once()


@pytest.mark.asyncio
async def test_sync_linear_not_authenticated():
    with patch("app.connectors.linear.get_settings") as mock_settings:
        settings = MagicMock()
        settings.linear_api_key = None
        mock_settings.return_value = settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/sync/linear")

    assert response.status_code == 401
