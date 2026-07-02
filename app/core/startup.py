import logging

from app.config import Settings

logger = logging.getLogger("spoon")


def validate_startup_config(settings: Settings) -> None:
    """Refuse to start in production when critical security settings are missing."""
    if not settings.is_production:
        if not settings.api_key:
            logger.warning(
                "SPOON_API_KEY is not set: every endpoint except /health and "
                "OAuth callbacks is reachable without authentication. Set "
                "SPOON_API_KEY before exposing Spoon beyond localhost."
            )
        if not settings.token_encryption_key:
            logger.warning(
                "SPOON_TOKEN_ENCRYPTION_KEY is not set: OAuth tokens are stored "
                "in plaintext on disk at %s. Set SPOON_TOKEN_ENCRYPTION_KEY to "
                "encrypt tokens at rest.",
                settings.token_store_path,
            )
        if settings.rate_limit_enabled and settings.rate_limit_backend == "memory":
            logger.info(
                "Rate limiting uses an in-memory store (SPOON_RATE_LIMIT_BACKEND=memory). "
                "If Spoon runs with multiple workers/replicas, set "
                "SPOON_RATE_LIMIT_BACKEND=redis with SPOON_REDIS_URL for limits "
                "to apply consistently across processes."
            )
        return

    missing: list[str] = []
    if not settings.api_key:
        missing.append("SPOON_API_KEY")
    if not settings.token_encryption_key:
        missing.append("SPOON_TOKEN_ENCRYPTION_KEY")

    if missing:
        raise RuntimeError(
            "Production startup blocked: set "
            + ", ".join(missing)
            + " before running with SPOON_ENV=production."
        )
