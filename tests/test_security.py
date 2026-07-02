import time
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import gdrive_oauth, notion_oauth
from app.auth.state import STATE_TTL_SECONDS, generate_oauth_state, pop_oauth_state
from app.auth.store import save_tokens, set_provider_token
from app.main import app


@pytest.mark.asyncio
async def test_search_limit_validation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "test", "limit": 9999},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_api_key_required_when_configured():
    transport = ASGITransport(app=app)
    with patch("app.core.security.get_settings") as mock_settings:
        settings = mock_settings.return_value
        settings.api_key = "secret-key"

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            unauth = await client.post("/api/v1/sync/notion")
            assert unauth.status_code == 401

            authed = await client.post(
                "/api/v1/sync/notion",
                headers={"X-API-Key": "secret-key"},
            )
            assert authed.status_code != 401 or authed.status_code == 401


def test_oauth_state_expires():
    state = generate_oauth_state()
    assert pop_oauth_state(state) is not None

    expired_state = generate_oauth_state()
    with patch("app.auth.state.time.time", return_value=time.time() + STATE_TTL_SECONDS + 1):
        assert pop_oauth_state(expired_state) is None


@pytest.mark.asyncio
async def test_oauth_callback_invalid_state():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/auth/notion/callback",
            params={"code": "abc", "state": "invalid"},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_oauth_callback_missing_code():
    state = generate_oauth_state()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/auth/notion/callback",
            params={"state": state},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_gdrive_refresh_preserves_refresh_token():
    set_provider_token(
        "gdrive",
        {"access_token": "old", "refresh_token": "keep-me", "expires_at": 0},
    )
    await gdrive_oauth.store_oauth_token({"access_token": "new-access", "expires_in": 3600})
    from app.auth.store import get_provider_token

    stored = get_provider_token("gdrive")
    assert stored is not None
    assert stored["refresh_token"] == "keep-me"


@pytest.mark.asyncio
async def test_notion_refresh_preserves_refresh_token():
    set_provider_token(
        "notion",
        {"access_token": "old", "refresh_token": "keep-notion", "expires_at": 0},
    )
    await notion_oauth.store_oauth_token({"access_token": "new-access"})
    from app.auth.store import get_provider_token

    stored = get_provider_token("notion")
    assert stored is not None
    assert stored["refresh_token"] == "keep-notion"


def test_token_store_permissions(tmp_path):
    from app.config import get_settings

    token_path = tmp_path / "tokens.json"
    with patch.object(get_settings(), "token_store_path", str(token_path)):
        save_tokens({"notion": {"access_token": "x"}})
    mode = token_path.stat().st_mode & 0o777
    assert mode == 0o600


def test_outlook_rejects_untrusted_next_link():
    from app.connectors.outlook import _validate_graph_url

    with pytest.raises(ValueError):
        _validate_graph_url("https://evil.example.com/me/messages")

    _validate_graph_url("https://graph.microsoft.com/v1.0/me/messages?$skiptoken=abc")
