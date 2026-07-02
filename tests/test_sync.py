from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


SAMPLE_PAGE = {
    "id": "page-1",
    "object": "page",
    "last_edited_time": "2024-01-01T00:00:00.000Z",
    "created_time": "2023-01-01T00:00:00.000Z",
    "properties": {
        "title": {
            "type": "title",
            "title": [{"plain_text": "Test Page"}],
        }
    },
}


@pytest.mark.asyncio
async def test_sync_notion_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": [], "has_more": False}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.connectors.notion.get_notion_access_token", return_value="test-token"),
        patch("app.connectors.notion.httpx.AsyncClient", return_value=mock_client),
        patch("app.connectors.notion.upload_documents") as mock_upload,
        patch("app.connectors.notion.get_settings") as mock_settings,
    ):
        settings = MagicMock()
        settings.notion_version = "2022-06-28"
        settings.max_block_depth = 10
        settings.max_content_length = 100_000
        settings.notion_api_key = "test-token"
        mock_settings.return_value = settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/sync/notion")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "notion"
    assert data["documents_processed"] == 0
    assert data["errors"] == []
    mock_upload.assert_called_once_with([])


@pytest.mark.asyncio
async def test_sync_notion_not_authenticated():
    with (
        patch("app.connectors.notion.get_notion_access_token", return_value=None),
        patch("app.auth.store.get_provider_token", return_value=None),
        patch("app.connectors.notion.get_settings") as mock_settings,
    ):
        settings = MagicMock()
        settings.notion_api_key = None
        mock_settings.return_value = settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/sync/notion")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sync_with_pages():
    search_response = MagicMock()
    search_response.status_code = 200
    search_response.json.return_value = {
        "results": [SAMPLE_PAGE],
        "has_more": False,
    }
    search_response.raise_for_status = MagicMock()

    blocks_response = MagicMock()
    blocks_response.status_code = 200
    blocks_response.json.return_value = {"results": [], "has_more": False}
    blocks_response.raise_for_status = MagicMock()

    call_count = 0

    async def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if method == "POST" and url.endswith("/search"):
            return search_response
        return blocks_response

    mock_client = AsyncMock()
    mock_client.request = mock_request
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.connectors.notion.get_notion_access_token", return_value="test-token"),
        patch("app.connectors.notion.httpx.AsyncClient", return_value=mock_client),
        patch("app.connectors.notion.upload_documents") as mock_upload,
        patch("app.connectors.notion.get_settings") as mock_settings,
        patch("app.auth.store.get_provider_token", return_value={"access_token": "test-token"}),
    ):
        settings = MagicMock()
        settings.notion_version = "2022-06-28"
        settings.max_block_depth = 10
        settings.max_content_length = 100_000
        settings.notion_api_key = "test-token"
        mock_settings.return_value = settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/sync/notion")

    assert response.status_code == 200
    data = response.json()
    assert data["documents_processed"] == 1
    mock_upload.assert_called_once()
    uploaded = mock_upload.call_args[0][0]
    assert len(uploaded) == 1
    assert uploaded[0].title == "Test Page"
