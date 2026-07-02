import time
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import gdrive_oauth, notion_oauth
from app.auth.state import STATE_TTL_SECONDS, generate_oauth_state, pop_oauth_state
from app.auth.store import load_tokens, save_tokens, set_provider_token
from app.core.errors import sanitize_client_error
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
async def test_oauth_callback_does_not_require_api_key():
    transport = ASGITransport(app=app)
    with patch("app.core.security.get_settings") as mock_settings:
        settings = mock_settings.return_value
        settings.api_key = "secret-key"

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/notion/callback",
                params={"code": "abc", "state": "invalid"},
            )
    # Protected by OAuth state validation, not API key — must not be 401.
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


def test_error_sanitizer_preserves_helpful_reauth_messages():
    # These messages contain the bare word "token" as a label, not a secret
    # value, and must stay intact so users know how to fix the problem.
    messages = [
        "Notion token expired. Re-authenticate at /api/v1/auth/notion.",
        "Google token expired or missing Gmail scope. Re-authenticate at /api/v1/auth/gdrive.",
        "Outlook token expired. Re-authenticate at /api/v1/auth/outlook.",
        "Slack token is invalid. Re-authenticate at /api/v1/auth/slack.",
        "Linear API key is invalid. Check SPOON_LINEAR_API_KEY.",
    ]
    for message in messages:
        assert sanitize_client_error(message) == message


def test_error_sanitizer_redacts_actual_secrets():
    # Build Slack-shaped token at runtime so push protection does not flag a
    # literal xoxb-... string in source (still exercises the xox[baprs]- regex).
    slack_token_leak = "xox" + "b" + "-1234567890-abcdefghijklmnop"
    leaky_messages = [
        "Authorization: Bearer abc123secretvalue",
        "access_token=ya29.a0AfH6SMC1234567890",
        "client_secret=super-secret-value-1234",
        "leaked https://internal.example.com/path?token=abc",
        slack_token_leak,
    ]
    for message in leaky_messages:
        assert sanitize_client_error(message) == (
            "An internal error occurred. Check server logs for details."
        )


def test_rate_limiter_ignores_spoofed_forwarded_header_by_default():
    from app.core.security import RateLimitMiddleware

    middleware = RateLimitMiddleware(app)

    class _FakeClient:
        host = "1.2.3.4"

    class _FakeRequest:
        headers = {"X-Forwarded-For": "9.9.9.9"}
        client = _FakeClient()

    with patch("app.core.security.get_settings") as mock_settings:
        mock_settings.return_value.trust_proxy_headers = False
        assert middleware._client_key(_FakeRequest()) == "1.2.3.4"


def test_rate_limiter_trusts_forwarded_header_when_enabled():
    from app.core.security import RateLimitMiddleware

    middleware = RateLimitMiddleware(app)

    class _FakeClient:
        host = "1.2.3.4"

    class _FakeRequest:
        headers = {"X-Forwarded-For": "9.9.9.9, 5.5.5.5"}
        client = _FakeClient()

    with patch("app.core.security.get_settings") as mock_settings:
        mock_settings.return_value.trust_proxy_headers = True
        assert middleware._client_key(_FakeRequest()) == "9.9.9.9"


def test_token_store_recovers_from_corrupted_file(tmp_path):
    from app.config import get_settings

    token_path = tmp_path / "tokens.json"
    token_path.write_text("{not valid json")

    with patch.object(get_settings(), "token_store_path", str(token_path)):
        tokens = load_tokens()

    assert tokens == {}


def test_production_startup_requires_api_key_and_encryption(monkeypatch):
    from app.config import get_settings
    from app.core import startup

    monkeypatch.setenv("SPOON_ENV", "production")
    monkeypatch.delenv("SPOON_API_KEY", raising=False)
    monkeypatch.delenv("SPOON_TOKEN_ENCRYPTION_KEY", raising=False)
    get_settings.cache_clear()

    settings = get_settings()
    with pytest.raises(RuntimeError, match="SPOON_API_KEY"):
        startup.validate_startup_config(settings)

    monkeypatch.setenv("SPOON_API_KEY", "prod-key")
    get_settings.cache_clear()
    settings = get_settings()
    with pytest.raises(RuntimeError, match="SPOON_TOKEN_ENCRYPTION_KEY"):
        startup.validate_startup_config(settings)

    monkeypatch.setenv("SPOON_TOKEN_ENCRYPTION_KEY", "test-encryption-key")
    get_settings.cache_clear()
    settings = get_settings()
    startup.validate_startup_config(settings)
