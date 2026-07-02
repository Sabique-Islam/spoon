import base64
from typing import Any

import httpx

from app.auth.state import generate_oauth_state, validate_oauth_state

__all__ = [
    "basic_auth_header",
    "exchange_token_form",
    "exchange_token_json",
    "generate_oauth_state",
    "validate_oauth_state",
]


def basic_auth_header(client_id: str, client_secret: str) -> str:
    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


async def exchange_token_form(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        response = await client.post(url, data=payload, timeout=30.0)
        response.raise_for_status()
        return response.json()


async def exchange_token_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers, timeout=30.0)
        response.raise_for_status()
        return response.json()
