from typing import Any
from urllib.parse import urlencode

import httpx

from app.auth.oauth import generate_oauth_state
from app.auth.store import get_provider_token, set_provider_token
from app.config import get_settings

SLACK_AUTH_URL = "https://slack.com/oauth/v2/authorize"
SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"
PROVIDER = "slack"

SLACK_SCOPES = ",".join(
    [
        "channels:history",
        "groups:history",
        "im:history",
        "mpim:history",
        "channels:read",
        "groups:read",
        "users:read",
    ]
)


def build_authorization_url() -> str:
    settings = get_settings()
    if not settings.slack_oauth_configured:
        raise ValueError("Slack OAuth is not configured")

    params = {
        "client_id": settings.slack_client_id,
        "scope": SLACK_SCOPES,
        "redirect_uri": settings.slack_oauth_redirect_uri,
        "state": generate_oauth_state(),
    }
    return f"{SLACK_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    settings = get_settings()
    payload = {
        "client_id": settings.slack_client_id,
        "client_secret": settings.slack_client_secret,
        "code": code,
        "redirect_uri": settings.slack_oauth_redirect_uri,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(SLACK_TOKEN_URL, data=payload, timeout=30.0)
        response.raise_for_status()
        data = response.json()

    if not data.get("ok"):
        raise ValueError(data.get("error", "Slack OAuth token exchange failed"))
    return data


async def store_oauth_token(token_response: dict[str, Any]) -> None:
    team = token_response.get("team") or {}
    set_provider_token(
        PROVIDER,
        {
            "access_token": token_response["access_token"],
            "bot_user_id": token_response.get("bot_user_id"),
            "team_id": team.get("id"),
            "team_name": team.get("name"),
            "scope": token_response.get("scope"),
        },
    )


async def get_slack_access_token() -> str | None:
    settings = get_settings()
    stored = get_provider_token(PROVIDER)
    if stored and stored.get("access_token"):
        return stored["access_token"]
    if settings.slack_bot_token:
        return settings.slack_bot_token
    return None
