import json
from pathlib import Path
from typing import Any

from app.config import get_settings


def _store_path() -> Path:
    path = Path(get_settings().token_store_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_tokens() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_tokens(tokens: dict[str, Any]) -> None:
    path = _store_path()
    path.write_text(json.dumps(tokens, indent=2))


def get_provider_token(provider: str) -> dict[str, Any] | None:
    tokens = load_tokens()
    return tokens.get(provider)


def set_provider_token(provider: str, token_data: dict[str, Any]) -> None:
    tokens = load_tokens()
    tokens[provider] = token_data
    save_tokens(tokens)


def delete_provider_token(provider: str) -> None:
    tokens = load_tokens()
    tokens.pop(provider, None)
    save_tokens(tokens)
