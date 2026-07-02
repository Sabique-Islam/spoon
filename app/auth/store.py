import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

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


@contextmanager
def _token_store_lock(path: Path) -> Iterator[None]:
    """Exclusive lock for read-modify-write across Uvicorn workers."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        try:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        except ImportError:
            # Windows and other platforms without fcntl: proceed without locking.
            logger.debug("fcntl unavailable; token store lock skipped")
        try:
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except ImportError:
                pass


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


def _read_tokens_unlocked(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    raw = path.read_text()
    if raw.startswith("gAAAA"):
        decrypted = _decrypt(raw)
        if decrypted is None:
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


def _write_tokens_unlocked(path: Path, tokens: dict[str, Any]) -> None:
    payload = json.dumps(tokens, indent=2)
    encrypted = _encrypt(payload)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(encrypted)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)
    _set_permissions(path)


def load_tokens() -> dict[str, Any]:
    path = _store_path()
    with _token_store_lock(path):
        return _read_tokens_unlocked(path)


def save_tokens(tokens: dict[str, Any]) -> None:
    path = _store_path()
    with _token_store_lock(path):
        _write_tokens_unlocked(path, tokens)


def get_provider_token(provider: str) -> dict[str, Any] | None:
    tokens = load_tokens()
    return tokens.get(provider)


def set_provider_token(provider: str, token_data: dict[str, Any]) -> None:
    path = _store_path()
    with _token_store_lock(path):
        tokens = _read_tokens_unlocked(path)
        tokens[provider] = token_data
        _write_tokens_unlocked(path, tokens)


def delete_provider_token(provider: str) -> None:
    path = _store_path()
    with _token_store_lock(path):
        tokens = _read_tokens_unlocked(path)
        tokens.pop(provider, None)
        _write_tokens_unlocked(path, tokens)
