import json
import logging
import os
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger("spoon")

_fernet = None


def _store_path() -> Path:
    path = Path(get_settings().token_store_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet

    settings = get_settings()
    if not settings.token_encryption_key:
        return None

    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.error("cryptography package required for token encryption")
        return None

    _fernet = Fernet(settings.token_encryption_key.encode())
    return _fernet


def _encrypt(data: str) -> str:
    fernet = _get_fernet()
    if not fernet:
        return data
    return fernet.encrypt(data.encode()).decode()


def _decrypt(data: str) -> str:
    fernet = _get_fernet()
    if not fernet:
        return data
    try:
        return fernet.decrypt(data.encode()).decode()
    except Exception:
        logger.warning("Failed to decrypt token store; treating as plaintext")
        return data


def _set_permissions(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
        os.chmod(path.parent, 0o700)
    except OSError:
        pass


def load_tokens() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {}
    raw = path.read_text()
    if raw.startswith("gAAAA"):
        raw = _decrypt(raw)
    return json.loads(raw)


def save_tokens(tokens: dict[str, Any]) -> None:
    path = _store_path()
    payload = json.dumps(tokens, indent=2)
    encrypted = _encrypt(payload)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(encrypted)
    tmp.replace(path)
    _set_permissions(path)


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
