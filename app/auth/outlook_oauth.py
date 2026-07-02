from typing import Any
from urllib.parse import urlencode

import httpx

from app.auth.oauth import exchange_token_form, generate_oauth_state
from app.auth.store import get_provider_token, set_provider_token
from app.config import get_settings

OUTLOOK_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
OUTLOOK_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
OUTLOOK_SCOPE_LIST = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/User.Read",
    "offline_access",
]
OUTLOOK_SCOPES = " ".join(OUTLOOK_SCOPE_LIST)
PROVIDER = "outlook"


def build_authorization_url() -> str:
    settings = get_settings()
    if not settings.outlook_oauth_configured:
        raise ValueError("Outlook OAuth is not configured")

    params = {
        "client_id": settings.outlook_connection_client_id,
        "redirect_uri": settings.outlook_oauth_redirect_uri,
        "response_type": "code",
        "scope": OUTLOOK_SCOPES,
        "response_mode": "query",
        "state": generate_oauth_state(),
    }
    return f"{OUTLOOK_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    settings = get_settings()
    payload = {
        "client_id": settings.outlook_connection_client_id,
        "client_secret": settings.outlook_connection_secret_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.outlook_oauth_redirect_uri,
    }
    return await exchange_token_form(OUTLOOK_TOKEN_URL, payload)


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    settings = get_settings()
    payload = {
        "client_id": settings.outlook_connection_client_id,
        "client_secret": settings.outlook_connection_secret_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": OUTLOOK_SCOPES,
    }
    return await exchange_token_form(OUTLOOK_TOKEN_URL, payload)


async def store_oauth_token(token_response: dict[str, Any]) -> None:
    existing = get_provider_token(PROVIDER) or {}
    set_provider_token(
        PROVIDER,
        {
            "access_token": token_response["access_token"],
            "refresh_token": token_response.get("refresh_token")
            or existing.get("refresh_token"),
            "expires_in": token_response.get("expires_in"),
            "token_type": token_response.get("token_type"),
        },
    )


async def get_outlook_access_token() -> str | None:
    stored = get_provider_token(PROVIDER)
    if stored and stored.get("access_token"):
        return stored["access_token"]
    return None


async def refresh_outlook_token_if_needed() -> str | None:
    settings = get_settings()
    stored = get_provider_token(PROVIDER)
    if not stored or not stored.get("refresh_token"):
        return await get_outlook_access_token()

    if not settings.outlook_oauth_configured:
        return stored.get("access_token")

    try:
        token_response = await refresh_access_token(stored["refresh_token"])
        await store_oauth_token(token_response)
        return token_response["access_token"]
    except httpx.HTTPError:
        return stored.get("access_token")
