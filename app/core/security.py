import logging
import secrets
import time
from collections import defaultdict
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.config import get_settings

logger = logging.getLogger("spoon")

# Rate limits: path prefix -> (max_requests, window_seconds)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/v1/sync": (6, 60),
    "/api/v1/search": (30, 60),
    "/api/v1/auth": (20, 60),
}

_redis_client = None


def _get_redis():
    """Lazily create a Redis client for distributed rate limiting.

    Mirrors the pattern used by app.auth.state so rate limiting keeps working
    correctly across multiple Uvicorn workers / container replicas, not just
    a single in-memory process.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    settings = get_settings()
    if settings.rate_limit_backend != "redis" or not settings.redis_url:
        return None

    try:
        import redis
    except ImportError:
        logger.error("redis package required for SPOON_RATE_LIMIT_BACKEND=redis")
        return None

    _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _client_key(self, request: Request) -> str:
        settings = get_settings()
        # Only trust X-Forwarded-For when Spoon is explicitly configured to run
        # behind a reverse proxy that overwrites/strips this header itself.
        # Otherwise any client can spoof it and get a fresh rate-limit bucket
        # on every request, completely bypassing the limiter.
        if settings.trust_proxy_headers:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    def _limit_for_path(self, path: str) -> tuple[int, int] | None:
        for prefix, limit in RATE_LIMITS.items():
            if path.startswith(prefix):
                return limit
        return None

    def _bucket_key(self, request: Request) -> str:
        path = request.url.path
        segment = path.split("/")[3] if len(path.split("/")) > 3 else "root"
        return f"{self._client_key(request)}:{segment}"

    def _is_rate_limited_redis(self, client, key: str, max_requests: int, window: int) -> bool:
        redis_key = f"ratelimit:{key}"
        now = time.time()
        window_start = now - window
        pipe = client.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, count = pipe.execute()
        if count >= max_requests:
            return True
        client.zadd(redis_key, {str(now): now})
        client.expire(redis_key, window)
        return False

    def _is_rate_limited_memory(self, key: str, max_requests: int, window: int) -> bool:
        now = time.time()
        window_start = now - window
        timestamps = [ts for ts in self._requests[key] if ts > window_start]
        if len(timestamps) >= max_requests:
            self._requests[key] = timestamps
            return True
        timestamps.append(now)
        self._requests[key] = timestamps
        return False

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not get_settings().rate_limit_enabled:
            return await call_next(request)

        limit = self._limit_for_path(request.url.path)
        if limit:
            max_requests, window = limit
            key = self._bucket_key(request)

            redis_client = _get_redis()
            if redis_client is not None:
                limited = self._is_rate_limited_redis(redis_client, key, max_requests, window)
            else:
                limited = self._is_rate_limited_memory(key, max_requests, window)

            if limited:
                return Response(
                    content='{"error":"Rate limit exceeded"}',
                    status_code=429,
                    media_type="application/json",
                )

        return await call_next(request)


def _extract_api_key(request: Request) -> str | None:
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


async def require_api_key(request: Request) -> None:
    settings = get_settings()
    if not settings.api_key:
        return

    provided = _extract_api_key(request)
    # secrets.compare_digest runs in constant time regardless of where the
    # strings first differ, avoiding a timing side-channel on the API key.
    if not provided or not secrets.compare_digest(provided, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid or missing API key"},
        )


ApiKeyDep = Depends(require_api_key)
