# `app/core/security.py`

**Source:** [`app/core/security.py`](../../app/core/security.py)  
**Lines:** 85

## Purpose

Provides optional API key authentication for FastAPI routes and in-memory per-IP rate limiting for sync, search, and auth endpoints.

## Role in the stack

| Component | Type | Scope |
| --- | --- | --- |
| `RateLimitMiddleware` | ASGI middleware | Paths matching `RATE_LIMITS` prefixes |
| `require_api_key` | FastAPI dependency | Routes that declare `Depends(require_api_key)` |
| `ApiKeyDep` | Alias | Shorthand `Depends(require_api_key)` (unused in routes — inline Depends used) |

Registered in [main.md](../main.md) before request logging middleware.

## Dependencies

| Import | Purpose |
| --- | --- |
| `time`, `defaultdict` | Sliding window rate limit storage |
| `Callable` | Middleware dispatch typing |
| `Depends`, `HTTPException`, `Request`, `status` | FastAPI auth dependency |
| `BaseHTTPMiddleware`, `Response` | Starlette middleware |
| `get_settings` | `api_key`, `rate_limit_enabled` |

## Rate limit configuration

| Path prefix | Max requests | Window (seconds) |
| --- | --- | --- |
| `/api/v1/sync` | 6 | 60 |
| `/api/v1/search` | 30 | 60 |
| `/api/v1/auth` | 20 | 60 |

Paths outside these prefixes are not rate limited by this middleware.

## Line-by-line reference

| Lines | Code | Behavior |
| --- | --- | --- |
| 1–3 | Imports | time, defaultdict, Callable |
| 5–7 | FastAPI/Starlette imports | Middleware and auth |
| 9 | `get_settings` import | Config access |
| 11–16 | `RATE_LIMITS` | Prefix → (max, window_seconds) map |
| 19–22 | `RateLimitMiddleware.__init__` | In-memory `defaultdict(list)` of timestamps |
| 24–30 | `_client_key()` | `X-Forwarded-For` first hop, else `request.client.host`, else `"unknown"` |
| 32–36 | `_limit_for_path()` | Longest matching prefix wins (iteration order) |
| 38–58 | `dispatch()` | Rate limit logic |
| 39–40 | Disabled check | Pass through if `rate_limit_enabled` is false |
| 42–43 | Path limit lookup | No limit → pass through |
| 44 | Unpack limit | `max_requests`, `window` |
| 45 | Rate limit key | `{client_ip}:{path_segment_3}` — e.g. sync/search/auth bucket |
| 46–47 | Window start | `now - window` |
| 48 | Prune timestamps | Keep only requests inside window |
| 49–54 | Limit exceeded | 429 JSON `{"error":"Rate limit exceeded"}` |
| 55–56 | Record request | Append `now`, store back |
| 58 | Pass through | Call next handler |
| 61–68 | `_extract_api_key()` | `X-API-Key` header or `Authorization: Bearer` |
| 71–81 | `require_api_key()` | Async dependency |
| 73–74 | No configured key | Allow all requests |
| 76–77 | Compare keys | Exact string match |
| 78–81 | Failure | 401 `{ "error": "Invalid or missing API key" }` |
| 84 | `ApiKeyDep` | Exported alias for Depends |

## Rate limit key structure

For path `/api/v1/sync/notion`:

- Client key: IP from `X-Forwarded-For` or direct client
- Bucket segment: `sync` (index `[3]` after split by `/`)
- Full key example: `203.0.113.1:sync`

Separate providers under `/sync/{provider}` share the same bucket (`sync`).

## Tradeoffs

| Choice | Benefit | Cost |
| --- | --- | --- |
| In-memory store | Zero external deps | Not shared across workers; resets on restart |
| Optional API key | Dev-friendly | Easy to deploy without auth |
| Prefix-based limits | Simple config | `/api/v1/health` unlimited |
| Forwarded-For trust | Works behind proxy | Spoofable if proxy does not strip client header |
| Plain 429 body | Minimal | No `Retry-After` header |

## Security notes

- Set `SPOON_API_KEY` in production; unset key disables all route protection.
- Terminate TLS at a trusted proxy and configure it to set `X-Forwarded-For` correctly.
- Rate limits are per-process — horizontal scaling multiplies effective quota.
- API key sent as Bearer is equivalent to `X-API-Key`; both appear in access logs if logged elsewhere.
- OAuth routes require API key when configured — ensure OAuth clients can supply it.

## Extension guide

1. **Redis rate limits:** Replace `self._requests` with Redis INCR + EXPIRE keyed by client + route.
2. **Constant-time compare:** Use `secrets.compare_digest` for API key comparison.
3. **Per-route limits:** Add finer prefixes (e.g. `/api/v1/sync/notion`) to `RATE_LIMITS`.
4. **Retry-After:** Set header on 429 from `window - (now - oldest_timestamp)`.
5. **API key hashing:** Store hash in config; compare hashed provided key.
6. **Disable auth for callback:** Split OAuth callback to a router without `require_api_key` if browser flow required.

## Related documentation

- [config.md](../config.md) — `api_key`, `rate_limit_enabled`
- [main.md](../main.md) — middleware registration order
- [routes.md](../routes.md) — `Depends(require_api_key)` on protected routes
