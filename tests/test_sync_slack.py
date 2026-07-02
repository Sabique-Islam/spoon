from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_sync_slack_success():
    async def mock_api_call(_client, _token, method, **params):
        if method == "users.list":
            return {
                "ok": True,
                "members": [
                    {
                        "id": "U1",
                        "name": "alice",
                        "profile": {
                            "display_name": "alice",
                            "real_name": "Alice",
                            "email": "alice@acme.com",
                        },
                    }
                ],
            }
        if method == "conversations.list":
            return {
                "ok": True,
                "channels": [
                    {
                        "id": "C1",
                        "name": "general",
                        "is_private": False,
                        "topic": {"value": "Announcements"},
                    }
                ],
            }
        if method == "team.info":
            return {
                "ok": True,
                "team": {"id": "T1", "name": "Acme", "domain": "acme"},
            }
        if method == "conversations.history":
            return {
                "ok": True,
                "messages": [{"user": "U1", "ts": "1609459200.000000", "text": "hello"}],
            }
        if method == "usergroups.list":
            return {
                "ok": True,
                "usergroups": [
                    {
                        "id": "S1",
                        "handle": "eng",
                        "name": "Engineering",
                        "users": ["U1"],
                    }
                ],
            }
        if method == "files.list":
            return {
                "ok": True,
                "files": [
                    {
                        "id": "F1",
                        "name": "notes.txt",
                        "title": "Notes",
                        "user": "U1",
                        "permalink": "https://acme.slack.com/files/F1",
                    }
                ],
                "paging": {"page": 1, "pages": 1},
            }
        if method == "emoji.list":
            return {"ok": True, "emoji": {"wave": "https://emoji/wave.png"}}
        if method in {"pins.list", "bookmarks.list", "conversations.members", "files.remote.list"}:
            return {"ok": True, "items": [], "bookmarks": [], "members": [], "files": []}
        raise ValueError(f"unexpected method {method}")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.connectors.slack.get_provider_token", return_value={"access_token": "xoxb-test"}),
        patch("app.connectors.slack.httpx.AsyncClient", return_value=mock_client),
        patch("app.connectors.base.upload_documents") as mock_upload,
        patch("app.connectors.slack.SlackConnector._api_call", side_effect=mock_api_call),
        patch("app.connectors.slack.get_slack_access_token", new=AsyncMock(return_value="xoxb-test")),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/sync/slack")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "slack"
    assert data["documents_processed"] == 6
    assert data["errors"] == []
    mock_upload.assert_called_once()
    uploaded_docs = mock_upload.call_args[0][0]
    object_types = {doc.metadata["object_type"] for doc in uploaded_docs}
    assert object_types == {"team", "user", "usergroup", "file", "emoji", "channel"}


@pytest.mark.asyncio
async def test_sync_slack_not_authenticated():
    with (
        patch("app.connectors.slack.get_provider_token", return_value=None),
        patch("app.connectors.slack.get_settings") as mock_settings,
    ):
        settings = MagicMock()
        settings.slack_bot_token = None
        mock_settings.return_value = settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/sync/slack")

    assert response.status_code == 401
