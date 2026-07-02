# `app/core/security.py`

**Source:** [`app/core/security.py`](../../app/core/security.py)  
**Lines:** ~150

## Purpose

Provides optional API key authentication for FastAPI routes and per-client rate limiting for sync, search, and auth endpoints. Rate limiting supports two backends: an in-memory sliding window (default, single-process) and a Redis-backed sliding window (for multi-worker/multi-replica deployments).

> **Updated during the July 2026 security audit follow-up:** the rate limiter no longer trusts a client-spoofable `X-Forwarded-For` header by default, the API key comparison is now constant-time, and a distributed Redis backend was added.

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
| `logging` | Warn when the Redis backend is requested but the `redis` package is missing |
| `secrets` | `secrets.compare_digest` for constant-time API key comparison |
| `time`, `defaultdict` | In-memory sliding window rate limit storage |
| `Callable` | Middleware dispatch typing |
| `Depends`, `HTTPException`, `Request`, `status` | FastAPI auth dependency |
| `BaseHTTPMiddleware`, `Response` | Starlette middleware |
| `get_settings` | `api_key`, `rate_limit_enabled`, `rate_limit_backend`, `trust_proxy_headers`, `redis_url` |
| `redis` (optional, imported lazily) | Distributed rate-limit counters when `SPOON_RATE_LIMIT_BACKEND=redis` |

## Rate limit configuration

| Path prefix | Max requests | Window (seconds) |
| --- | --- | --- |
| `/api/v1/sync` | 6 | 60 |
| `/api/v1/search` | 30 | 60 |
| `/api/v1/auth` | 20 | 60 |

Paths outside these prefixes are not rate limited by this middleware.

## Line-by-line reference

| Section | Code | Behavior |
| --- | --- | --- |
| Imports | `logging`, `secrets`, `time`, `defaultdict`, `Callable`, FastAPI/Starlette, `get_settings` | Standard + framework imports |
| `RATE_LIMITS` | Prefix → `(max, window_seconds)` map | Unchanged from earlier version |
| `_get_redis()` | Lazily builds a `redis.from_url(...)` client | Only activates when `settings.rate_limit_backend == "redis"` **and** `settings.redis_url` is set. Logs an error (once, via `ImportError`) if `redis` isn't installed. Mirrors the exact pattern used in `app/auth/state.py`. |
| `RateLimitMiddleware.__init__` | `defaultdict(list)` | In-memory fallback store, always initialized even if Redis is used elsewhere in the process |
| `_client_key()` | See below | **Now settings-gated**: only reads `X-Forwarded-For` when `settings.trust_proxy_headers` is `True`. Otherwise always uses `request.client.host`. |
| `_limit_for_path()` | Longest-prefix-ish match (iteration order of dict) | Unchanged |
| `_bucket_key()` | `f"{client_key}:{path_segment_3}"` | Extracted into its own helper so both backends share the same key derivation |
| `_is_rate_limited_redis()` | `ZREMRANGEBYSCORE` + `ZCARD` + `ZADD` + `EXPIRE` on a sorted set | Sliding-window counter shared across all processes talking to the same Redis instance |
| `_is_rate_limited_memory()` | List of timestamps, pruned to the current window | Original single-process algorithm, used when Redis isn't configured |
| `dispatch()` | Disabled check → path lookup → pick backend → 429 or pass through | Chooses `_is_rate_limited_redis` if a Redis client is available, else `_is_rate_limited_memory` |
| `_extract_api_key()` | `X-API-Key` header or `Authorization: Bearer` | Unchanged |
| `require_api_key()` | `secrets.compare_digest(provided, settings.api_key)` | **Now constant-time.** Previously used `!=`, which is a very weak timing side-channel (see Security notes). |
| `ApiKeyDep` | Exported alias for `Depends(require_api_key)` | Unchanged |

## `_client_key()` — before vs. after

```python
# Before (vulnerable to spoofing from any client):
forwarded = request.headers.get("X-Forwarded-For")
if forwarded:
    return forwarded.split(",")[0].strip()

# After (only trusts the header when explicitly configured):
if settings.trust_proxy_headers:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
```

Any client can set an arbitrary `X-Forwarded-For` header on a direct request. Without a trusted reverse proxy in front of Spoon that strips/overwrites this header, trusting it blindly lets an attacker get a fresh rate-limit bucket on every request — a total bypass. `SPOON_TRUST_PROXY_HEADERS=true` should only be set when Spoon is deployed behind a proxy (nginx, ALB, Cloudflare, etc.) that is configured to always set this header itself and reject client-supplied values.

## Rate limit key structure

For path `/api/v1/sync/notion`:

- Client key: `request.client.host` by default, or first `X-Forwarded-For` hop if `SPOON_TRUST_PROXY_HEADERS=true`
- Bucket segment: `sync` (index `[3]` after split by `/`)
- Full key example: `203.0.113.1:sync`

Separate providers under `/sync/{provider}` share the same bucket (`sync`).

## Tradeoffs

| Choice | Benefit | Cost |
| --- | --- | --- |
| In-memory store (default) | Zero external deps | Not shared across workers/replicas; resets on restart |
| Optional Redis backend | Correct limits across multiple workers/replicas | Extra operational dependency; two code paths to test |
| `trust_proxy_headers` opt-in | Closed by default — safe out of the box | Operators behind a real proxy must remember to enable it |
| Optional API key | Dev-friendly | Easy to deploy without auth (mitigated by startup warning in `main.py`) |
| Prefix-based limits | Simple config | `/api/v1/health` unlimited |
| `secrets.compare_digest` | Removes timing side-channel | Negligible CPU cost difference |
| Plain 429 body | Minimal | No `Retry-After` header |

## Security notes

- Set `SPOON_API_KEY` in production; unset key disables all route protection (a startup warning is now logged from `app/main.py` if it's unset, and a `CRITICAL` log if `SPOON_ENV=production` with no key).
- Only set `SPOON_TRUST_PROXY_HEADERS=true` behind a reverse proxy that itself overwrites `X-Forwarded-For` — otherwise rate limiting is trivially bypassable.
- For multi-worker/multi-replica deployments, set `SPOON_RATE_LIMIT_BACKEND=redis` with `SPOON_REDIS_URL` so limits are enforced consistently; the in-memory backend is per-process.
- API key comparison uses `secrets.compare_digest`, which is constant-time and removes the (low-severity but easy-to-fix) timing side-channel present in a naive `!=` comparison.
- API key sent as Bearer is equivalent to `X-API-Key`; both appear in access logs if logged elsewhere.
- OAuth routes require API key when configured — ensure OAuth clients can supply it.

## Extension guide

1. **Per-route limits:** Add finer prefixes (e.g. `/api/v1/sync/notion`) to `RATE_LIMITS`.
2. **Retry-After:** Set header on 429 from `window - (now - oldest_timestamp)` (works for both backends, but requires tracking the oldest timestamp in the Redis path too).
3. **API key hashing:** Store hash in config; compare hashed provided key.
4. **Disable auth for callback:** Split OAuth callback to a router without `require_api_key` if browser flow required.
5. **Trusted proxy allowlist:** If you need finer control than a boolean, extend `_client_key()` to check `request.client.host` against a configured list of trusted proxy IPs before honoring `X-Forwarded-For`.

## Related documentation

- [config.md](../config.md) — `api_key`, `rate_limit_enabled`, `rate_limit_backend`, `trust_proxy_headers`
- [main.md](../main.md) — middleware registration order, startup warnings
- [routes.md](../routes.md) — `Depends(require_api_key)` on protected routes
- [auth/state.md](../auth/state.md) — sibling Redis-backed pattern for OAuth CSRF state
