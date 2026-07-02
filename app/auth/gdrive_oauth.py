from typing import Any
from urllib.parse import urlencode

import httpx

from app.auth.oauth import exchange_token_form, generate_oauth_state
from app.auth.store import get_provider_token, set_provider_token
from app.config import get_settings

GDRIVE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GDRIVE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPE_LIST = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]
GOOGLE_SCOPES = " ".join(GOOGLE_SCOPE_LIST)
GDRIVE_SCOPES = GOOGLE_SCOPES
PROVIDER = "gdrive"


def build_authorization_url() -> str:
    settings = get_settings()
    if not settings.gdrive_oauth_configured:
        raise ValueError("Google Drive OAuth is not configured")

    params = {
        "client_id": settings.gdrive_connection_client_id,
        "redirect_uri": settings.gdrive_oauth_redirect_uri,
        "response_type": "code",
        "scope": GDRIVE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": generate_oauth_state(),
    }
    return f"{GDRIVE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    settings = get_settings()
    payload = {
        "client_id": settings.gdrive_connection_client_id,
        "client_secret": settings.gdrive_connection_secret_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.gdrive_oauth_redirect_uri,
    }
    return await exchange_token_form(GDRIVE_TOKEN_URL, payload)


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    settings = get_settings()
    payload = {
        "client_id": settings.gdrive_connection_client_id,
        "client_secret": settings.gdrive_connection_secret_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    return await exchange_token_form(GDRIVE_TOKEN_URL, payload)


async def store_oauth_token(token_response: dict[str, Any]) -> None:
    set_provider_token(
        PROVIDER,
        {
            "access_token": token_response["access_token"],
            "refresh_token": token_response.get("refresh_token"),
            "expires_in": token_response.get("expires_in"),
            "token_type": token_response.get("token_type"),
        },
    )


async def get_gdrive_access_token() -> str | None:
    stored = get_provider_token(PROVIDER)
    if stored and stored.get("access_token"):
        return stored["access_token"]
    return None


def has_service_account_fallback() -> bool:
    settings = get_settings()
    if not settings.gdrive_api_key:
        return False
    from pathlib import Path

    return Path(settings.gdrive_api_key).is_file()


async def refresh_gdrive_token_if_needed() -> str | None:
    settings = get_settings()
    stored = get_provider_token(PROVIDER)
    if not stored or not stored.get("refresh_token"):
        return await get_gdrive_access_token()

    if not settings.gdrive_oauth_configured:
        return stored.get("access_token")

    try:
        token_response = await refresh_access_token(stored["refresh_token"])
        await store_oauth_token(token_response)
        return token_response["access_token"]
    except httpx.HTTPError:
        return stored.get("access_token")
