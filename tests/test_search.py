from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_search():
    mock_results = [{"id": "doc-1", "content": "matching content"}]

    with patch("app.routes.search_documents", return_value=mock_results):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/search",
                json={"query": "test query", "limit": 5},
            )

    assert response.status_code == 200
    assert response.json() == {"results": mock_results}


@pytest.mark.asyncio
async def test_search_failure():
    with patch(
        "app.routes.search_documents",
        side_effect=Exception("API error"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/search",
                json={"query": "test"},
            )

    assert response.status_code == 502
