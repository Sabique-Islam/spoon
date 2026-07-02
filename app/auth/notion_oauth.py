from typing import Any
from urllib.parse import urlencode

import httpx

from app.auth.oauth import (
    basic_auth_header,
    exchange_token_json,
    generate_oauth_state,
)
from app.auth.store import get_provider_token, set_provider_token
from app.config import get_settings

NOTION_AUTH_URL = "https://api.notion.com/v1/oauth/authorize"
NOTION_TOKEN_URL = "https://api.notion.com/v1/oauth/token"
PROVIDER = "notion"


def build_authorization_url() -> str:
    settings = get_settings()
    if not settings.notion_oauth_configured:
        raise ValueError("Notion OAuth is not configured")

    params = {
        "client_id": settings.notion_connection_client_id,
        "redirect_uri": settings.notion_oauth_redirect_uri,
        "response_type": "code",
        "owner": "user",
        "state": generate_oauth_state(),
    }
    return f"{NOTION_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    settings = get_settings()
    headers = {
        "Authorization": basic_auth_header(
            settings.notion_connection_client_id or "",
            settings.notion_connection_secret_id or "",
        ),
        "Content-Type": "application/json",
    }
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.notion_oauth_redirect_uri,
    }
    return await exchange_token_json(NOTION_TOKEN_URL, payload, headers)


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    settings = get_settings()
    headers = {
        "Authorization": basic_auth_header(
            settings.notion_connection_client_id or "",
            settings.notion_connection_secret_id or "",
        ),
        "Content-Type": "application/json",
    }
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    return await exchange_token_json(NOTION_TOKEN_URL, payload, headers)


async def store_oauth_token(token_response: dict[str, Any]) -> None:
    set_provider_token(
        PROVIDER,
        {
            "access_token": token_response["access_token"],
            "refresh_token": token_response.get("refresh_token"),
            "workspace_id": token_response.get("workspace_id"),
            "workspace_name": token_response.get("workspace_name"),
        },
    )


async def get_notion_access_token() -> str | None:
    settings = get_settings()
    stored = get_provider_token(PROVIDER)
    if stored and stored.get("access_token"):
        return stored["access_token"]
    if settings.notion_api_key:
        return settings.notion_api_key
    return None


async def refresh_notion_token_if_needed() -> str | None:
    settings = get_settings()
    stored = get_provider_token(PROVIDER)
    if not stored or not stored.get("refresh_token"):
        return await get_notion_access_token()

    if not settings.notion_oauth_configured:
        return stored.get("access_token")

    try:
        token_response = await refresh_access_token(stored["refresh_token"])
        await store_oauth_token(token_response)
        return token_response["access_token"]
    except httpx.HTTPError:
        return stored.get("access_token")
