import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.security import RateLimitMiddleware
from app.logging import RequestLoggingMiddleware, setup_logging
from app.routes import router

setup_logging()
logger = logging.getLogger("spoon")

settings = get_settings()
app = FastAPI(
    title="Spoon",
    version="1.0.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

if settings.cors_origins_list:
    # CORS is opt-in and explicit: no middleware is added (i.e. cross-origin
    # browser requests stay blocked) unless SPOON_CORS_ALLOWED_ORIGINS is set.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["X-API-Key", "Authorization", "Content-Type"],
    )

app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.include_router(router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


def _warn_on_insecure_config() -> None:
    if not settings.api_key:
        logger.warning(
            "SPOON_API_KEY is not set: every endpoint except /health is "
            "reachable without authentication. Set SPOON_API_KEY before "
            "exposing Spoon beyond localhost."
        )
    if not settings.token_encryption_key:
        logger.warning(
            "SPOON_TOKEN_ENCRYPTION_KEY is not set: OAuth tokens are stored "
            "in plaintext on disk at %s. Set SPOON_TOKEN_ENCRYPTION_KEY to "
            "encrypt tokens at rest.",
            settings.token_store_path,
        )
    if settings.is_production and not settings.api_key:
        logger.critical(
            "SPOON_ENV=production with no SPOON_API_KEY set. This deployment "
            "is fully open to the network. Set SPOON_API_KEY immediately."
        )
    if settings.rate_limit_enabled and settings.rate_limit_backend == "memory":
        logger.info(
            "Rate limiting uses an in-memory store (SPOON_RATE_LIMIT_BACKEND=memory). "
            "If Spoon runs with multiple workers/replicas, set "
            "SPOON_RATE_LIMIT_BACKEND=redis with SPOON_REDIS_URL for limits "
            "to apply consistently across processes."
        )


_warn_on_insecure_config()
