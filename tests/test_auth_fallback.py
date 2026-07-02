from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_auth_fallback_api_key():
    search_response = MagicMock()
    search_response.status_code = 200
    search_response.json.return_value = {"results": [], "has_more": False}
    search_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=search_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.auth.store.get_provider_token", return_value=None),
        patch("app.connectors.notion.get_notion_access_token", return_value="internal-token"),
        patch("app.connectors.notion.httpx.AsyncClient", return_value=mock_client),
        patch("app.connectors.notion.upload_documents"),
        patch("app.config.get_settings") as mock_settings,
    ):
        settings = MagicMock()
        settings.notion_api_key = "internal-token"
        settings.notion_version = "2022-06-28"
        settings.max_block_depth = 10
        settings.max_content_length = 100_000
        mock_settings.return_value = settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/sync/notion")

    assert response.status_code == 200
    assert response.json()["provider"] == "notion"
