from typing import Any
from urllib.parse import urlencode

import httpx

from app.auth.oauth import exchange_token_form, generate_oauth_state
from app.auth.pkce import generate_pkce_pair
from app.auth.store import get_provider_token, set_provider_token
from app.auth.token_utils import merge_oauth_token, token_needs_refresh
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

    verifier, challenge = generate_pkce_pair()
    params = {
        "client_id": settings.gdrive_connection_client_id,
        "redirect_uri": settings.gdrive_oauth_redirect_uri,
        "response_type": "code",
        "scope": GDRIVE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": generate_oauth_state(pkce_verifier=verifier),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{GDRIVE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_token(
    code: str, *, pkce_verifier: str | None = None
) -> dict[str, Any]:
    settings = get_settings()
    payload = {
        "client_id": settings.gdrive_connection_client_id,
        "client_secret": settings.gdrive_connection_secret_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.gdrive_oauth_redirect_uri,
    }
    if pkce_verifier:
        payload["code_verifier"] = pkce_verifier
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
        merge_oauth_token(
            PROVIDER,
            token_response,
            extra={"token_type": token_response.get("token_type")},
        ),
    )


async def get_gdrive_access_token() -> str | None:
    stored = get_provider_token(PROVIDER)
    if stored and stored.get("access_token"):
        return stored["access_token"]
    return None


def has_service_account_fallback() -> bool:
    from app.auth.google_service_account import has_service_account_fallback as _has

    return _has()


async def refresh_gdrive_token_if_needed() -> str | None:
    settings = get_settings()
    stored = get_provider_token(PROVIDER)
    if not stored or not stored.get("refresh_token"):
        return await get_gdrive_access_token()

    if not settings.gdrive_oauth_configured:
        return stored.get("access_token")

    if not token_needs_refresh(stored):
        return stored.get("access_token")

    try:
        token_response = await refresh_access_token(stored["refresh_token"])
        await store_oauth_token(token_response)
        return token_response["access_token"]
    except httpx.HTTPError:
        return stored.get("access_token")
