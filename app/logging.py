import logging
import sys
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("spoon")


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(handler)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


def log_sync(provider: str, count: int, duration_ms: float, errors: list[str]) -> None:
    logger.info(
        "sync provider=%s documents=%d duration_ms=%.1f errors=%d",
        provider,
        count,
        duration_ms,
        len(errors),
    )
    for error in errors:
        logger.error("sync error provider=%s: %s", provider, error)


def log_search(duration_ms: float) -> None:
    logger.info("search duration_ms=%.1f", duration_ms)
