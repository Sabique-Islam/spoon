import logging
import re

logger = logging.getLogger("spoon")

_MAX_SYNC_ERRORS = 50

# Patterns that may leak internal details if returned to clients.
_SENSITIVE_PATTERNS = (
    r"https?://[^\s]+",
    r"Bearer\s+\S+",
    r"xox[baprs]-\S+",
    r"ya29\.\S+",
    r"token[^\s]*",
    r"secret[^\s]*",
)


def sanitize_client_error(message: str, *, context: str = "") -> str:
    """Return a stable client-safe error message; log the original."""
    if context:
        logger.error("%s: %s", context, message)
    for pattern in _SENSITIVE_PATTERNS:
        if re.search(pattern, message, re.IGNORECASE):
            return "An internal error occurred. Check server logs for details."
    if len(message) > 200:
        return message[:200] + "..."
    return message


def sanitize_sync_errors(errors: list[str], *, provider: str) -> list[str]:
    sanitized: list[str] = []
    for error in errors[:_MAX_SYNC_ERRORS]:
        sanitized.append(
            sanitize_client_error(error, context=f"sync provider={provider}")
        )
    if len(errors) > _MAX_SYNC_ERRORS:
        sanitized.append(
            f"Additional errors truncated ({len(errors) - _MAX_SYNC_ERRORS} more)."
        )
    return sanitized
