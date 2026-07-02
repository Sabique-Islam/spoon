import logging
import re

logger = logging.getLogger("spoon")

_MAX_SYNC_ERRORS = 50

# Patterns that indicate an *actual secret value* is present, not just the
# word "token"/"secret" used as a label (e.g. "Notion token expired" must
# stay readable — only the credential material itself should be redacted).
_SENSITIVE_PATTERNS = (
    r"https?://[^\s]+",  # absolute URLs may embed query-string tokens/keys
    r"Bearer\s+\S+",  # Authorization header value
    r"xox[baprs]-\S+",  # Slack tokens (bot/user/app/refresh/legacy)
    r"ya29\.\S+",  # Google OAuth access token prefix
    r"AKIA[0-9A-Z]{16}",  # AWS access key id
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",  # PEM private key material
    r"\b(?:token|secret|password|api[_-]?key|client[_-]?secret)\s*[:=]\s*\S+",  # labeled secret assignment, e.g. "token=abc123" or "secret: xyz"
    r"\b[A-Za-z0-9_-]{40,}\b",  # long opaque strings (hashes/JWTs/keys) unlikely to be a normal sentence word
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
