import time
from typing import Any

from app.auth.store import get_provider_token


def merge_oauth_token(
    provider: str,
    token_response: dict[str, Any],
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = get_provider_token(provider) or {}
    data: dict[str, Any] = {
        "access_token": token_response["access_token"],
        "refresh_token": token_response.get("refresh_token")
        or existing.get("refresh_token"),
        "token_type": token_response.get("token_type") or existing.get("token_type"),
    }

    expires_in = token_response.get("expires_in")
    if expires_in is not None:
        data["expires_in"] = expires_in
        data["expires_at"] = time.time() + int(expires_in) - 60

    if extra:
        data.update(extra)

    return data


def token_needs_refresh(stored: dict[str, Any] | None) -> bool:
    if not stored:
        return False
    if not stored.get("refresh_token"):
        return False
    expires_at = stored.get("expires_at")
    if expires_at is None:
        return True
    return time.time() >= float(expires_at)
