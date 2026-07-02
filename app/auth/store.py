import json
import logging
import os
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger("spoon")

_fernet = None
_warned_plaintext = False


def _store_path() -> Path:
    path = Path(get_settings().token_store_path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # mkdir's `mode` is subject to the process umask, so explicitly enforce
    # the restrictive permission rather than relying on it alone.
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    return path


def _get_fernet():
    global _fernet, _warned_plaintext
    if _fernet is not None:
        return _fernet

    settings = get_settings()
    if not settings.token_encryption_key:
        if not _warned_plaintext:
            logger.warning(
                "SPOON_TOKEN_ENCRYPTION_KEY is not set; OAuth tokens are stored "
                "in plaintext at %s. Set SPOON_TOKEN_ENCRYPTION_KEY to encrypt "
                "tokens at rest (see .env.example).",
                get_settings().token_store_path,
            )
            _warned_plaintext = True
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


def _decrypt(data: str) -> str | None:
    fernet = _get_fernet()
    if not fernet:
        return data
    try:
        return fernet.decrypt(data.encode()).decode()
    except Exception:
        logger.warning("Failed to decrypt token store; treating as plaintext")
        return None


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
        decrypted = _decrypt(raw)
        if decrypted is None:
            # Wrong/rotated SPOON_TOKEN_ENCRYPTION_KEY or corrupted file.
            # Treat as "no tokens" (forces re-authentication) instead of
            # crashing every endpoint that needs to read a token.
            logger.critical(
                "Token store at %s could not be decrypted; ignoring stored "
                "tokens. Providers will need to be reconnected.",
                path,
            )
            return {}
        raw = decrypted

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.critical(
            "Token store at %s is corrupted (invalid JSON); ignoring stored "
            "tokens. Providers will need to be reconnected.",
            path,
        )
        return {}


def save_tokens(tokens: dict[str, Any]) -> None:
    path = _store_path()
    payload = json.dumps(tokens, indent=2)
    encrypted = _encrypt(payload)
    tmp = path.with_suffix(".tmp")
    # Create the temp file with restrictive permissions from the start so
    # there is no window where a freshly-written file is world/group
    # readable before the final chmod runs.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(encrypted)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
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
