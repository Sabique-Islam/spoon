import base64
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from app.auth.store import get_provider_token, set_provider_token
from app.config import get_settings

NOTION_AUTH_URL = "https://api.notion.com/v1/oauth/authorize"
NOTION_TOKEN_URL = "https://api.notion.com/v1/oauth/token"

_pending_states: set[str] = set()


def generate_oauth_state() -> str:
    state = secrets.token_urlsafe(32)
    _pending_states.add(state)
    return state


def validate_oauth_state(state: str) -> bool:
    if state in _pending_states:
        _pending_states.discard(state)
        return True
    return False


def build_authorization_url() -> str:
    settings = get_settings()
    if not settings.oauth_configured:
        raise ValueError("OAuth is not configured")

    params = {
        "client_id": settings.notion_connection_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "response_type": "code",
        "owner": "user",
        "state": generate_oauth_state(),
    }
    return f"{NOTION_AUTH_URL}?{urlencode(params)}"


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    settings = get_settings()
    headers = {
        "Authorization": _basic_auth_header(
            settings.notion_connection_client_id or "",
            settings.notion_connection_secret_id or "",
        ),
        "Content-Type": "application/json",
    }
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oauth_redirect_uri,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            NOTION_TOKEN_URL, json=payload, headers=headers, timeout=30.0
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    settings = get_settings()
    headers = {
        "Authorization": _basic_auth_header(
            settings.notion_connection_client_id or "",
            settings.notion_connection_secret_id or "",
        ),
        "Content-Type": "application/json",
    }
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            NOTION_TOKEN_URL, json=payload, headers=headers, timeout=30.0
        )
        response.raise_for_status()
        return response.json()


async def store_oauth_token(token_response: dict[str, Any]) -> None:
    set_provider_token(
        "notion",
        {
            "access_token": token_response["access_token"],
            "refresh_token": token_response.get("refresh_token"),
            "workspace_id": token_response.get("workspace_id"),
            "workspace_name": token_response.get("workspace_name"),
        },
    )


async def get_notion_access_token() -> str | None:
    settings = get_settings()
    stored = get_provider_token("notion")
    if stored and stored.get("access_token"):
        return stored["access_token"]
    if settings.notion_api_key:
        return settings.notion_api_key
    return None


async def refresh_notion_token_if_needed() -> str | None:
    settings = get_settings()
    stored = get_provider_token("notion")
    if not stored or not stored.get("refresh_token"):
        return await get_notion_access_token()

    if not settings.oauth_configured:
        return stored.get("access_token")

    try:
        token_response = await refresh_access_token(stored["refresh_token"])
        await store_oauth_token(token_response)
        return token_response["access_token"]
    except httpx.HTTPError:
        return stored.get("access_token")
