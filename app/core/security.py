import time
from collections import defaultdict
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.config import get_settings

# Rate limits: path prefix -> (max_requests, window_seconds)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/v1/sync": (6, 60),
    "/api/v1/search": (30, 60),
    "/api/v1/auth": (20, 60),
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _client_key(self, request: Request) -> str:
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

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not get_settings().rate_limit_enabled:
            return await call_next(request)

        limit = self._limit_for_path(request.url.path)
        if limit:
            max_requests, window = limit
            key = f"{self._client_key(request)}:{request.url.path.split('/')[3] if len(request.url.path.split('/')) > 3 else 'root'}"
            now = time.time()
            window_start = now - window
            timestamps = [ts for ts in self._requests[key] if ts > window_start]
            if len(timestamps) >= max_requests:
                return Response(
                    content='{"error":"Rate limit exceeded"}',
                    status_code=429,
                    media_type="application/json",
                )
            timestamps.append(now)
            self._requests[key] = timestamps

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
    if not provided or provided != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid or missing API key"},
        )


ApiKeyDep = Depends(require_api_key)
