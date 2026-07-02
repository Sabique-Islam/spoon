# `app/main.py`

**Source:** [`app/main.py`](../../app/main.py)  
**Lines:** ~65

## Purpose

Application entry point for the Spoon FastAPI service. Wires configuration, logging, middleware, API routes, and a global exception handler into a single ASGI app object consumed by Uvicorn (or any ASGI server).

> **Updated during the July 2026 security audit follow-up:** added an optional, opt-in `CORSMiddleware` block and a `_warn_on_insecure_config()` startup check that logs clear warnings (or a `CRITICAL` in production) when the app is about to run without an API key, without token encryption, or with a per-process (non-shared) rate limiter.

## Role in the stack

| Layer | Responsibility |
| --- | --- |
| Bootstrap | Calls `setup_logging()` before any request handling |
| Configuration | Loads cached `Settings` via `get_settings()` |
| HTTP surface | Mounts `/api/v1` router; disables OpenAPI UI in production |
| Cross-cutting | CORS (opt-in), rate limiting, and request logging middleware |
| Safety net | Catches unhandled exceptions and returns generic 500 JSON |
| **New:** Startup diagnostics | Logs insecure-configuration warnings before the app starts serving traffic |

## Dependencies

| Import | Module | Usage |
| --- | --- | --- |
| `logging` | stdlib | Module-level logger |
| `FastAPI`, `Request` | `fastapi` | App factory and exception handler typing |
| `CORSMiddleware` | `fastapi.middleware.cors` | **New.** Opt-in cross-origin support |
| `JSONResponse` | `fastapi.responses` | Error response body |
| `get_settings` | `app.config` | Environment-driven settings, including new `cors_origins_list`, `rate_limit_backend`, `token_encryption_key` checks |
| `RateLimitMiddleware` | `app.core.security` | Per-path rate limits |
| `RequestLoggingMiddleware`, `setup_logging` | `app.logging` | Structured request timing logs |
| `router` | `app.routes` | All REST endpoints |

## Line-by-line reference

| Section | Code | Behavior |
| --- | --- | --- |
| Imports | `logging`, FastAPI/CORS/JSONResponse, app imports | `CORSMiddleware` import added |
| `setup_logging()` | Configures `spoon` logger to stdout before app creation | Unchanged |
| `settings = get_settings()` | Loads `.env` / env vars once at import (cached) | Unchanged |
| `FastAPI(...)` | Creates app; hides `/docs` and `/redoc` when `env=production` | Unchanged |
| CORS block | `if settings.cors_origins_list: app.add_middleware(CORSMiddleware, ...)` | **New.** Only registers `CORSMiddleware` when `SPOON_CORS_ALLOWED_ORIGINS` is set. `allow_credentials=False` (Spoon uses header-based API keys, not cookies), explicit `allow_methods`/`allow_headers` allowlist rather than `"*"`. |
| `add_middleware(RateLimitMiddleware)` | Outermost added = runs first on request (Starlette LIFO) | Unchanged |
| `add_middleware(RequestLoggingMiddleware)` | Logs method, path, status, duration after inner handlers | Unchanged |
| `include_router(router, prefix="/api/v1")` | Mounts all routes under `/api/v1` | Unchanged |
| `@app.exception_handler(Exception)` | Logs full traceback; client sees `"Internal server error"` only | Unchanged |
| `_warn_on_insecure_config()` | See below | **New.** Called once at import time, after the app and middleware are fully constructed |

## `_warn_on_insecure_config()` — new startup diagnostics

| Condition | Log level | Message intent |
| --- | --- | --- |
| `settings.api_key` unset | `WARNING` | Every endpoint except `/health` is reachable without authentication |
| `settings.token_encryption_key` unset | `WARNING` | OAuth tokens are stored in plaintext on disk |
| `settings.is_production` **and** `settings.api_key` unset | `CRITICAL` | Production deployment is fully open to the network — escalated severity |
| `rate_limit_enabled` **and** `rate_limit_backend == "memory"` | `INFO` | Reminder that rate limits won't be shared across multiple workers/replicas |

This function makes previously **silent** footguns visible in logs at startup, without changing default behavior (the app still starts and runs in "dev mode" if you don't set these — it just tells you loudly that it did).

## Middleware order

Starlette applies middleware in reverse registration order. With CORS enabled:

```
Request → CORSMiddleware → RateLimitMiddleware → RequestLoggingMiddleware → routes → Response
```

Without `SPOON_CORS_ALLOWED_ORIGINS` set (the default), `CORSMiddleware` is never added:

```
Request → RateLimitMiddleware → RequestLoggingMiddleware → routes → Response
```

Rate limiting runs before logging so rejected (429) requests still get logged by the inner middleware.

## Tradeoffs

| Choice | Benefit | Cost |
| --- | --- | --- |
| Global `Exception` handler | Prevents stack trace leakage to clients | Masks all unhandled errors as 500; no per-exception typing |
| Disable docs in production | Reduces attack surface and info disclosure | Operators must use external API docs or staging |
| Settings at module import | Fast startup; single cached instance | Settings changes require process restart |
| CORS opt-in, not default-open | Safe by default; no accidental `allow_origins=["*"]` | Browser-based frontends must explicitly configure `SPOON_CORS_ALLOWED_ORIGINS` |
| `allow_credentials=False` in CORS config | Avoids the unsafe `allow_origins=["*"] + allow_credentials=True` combination entirely | Not suitable if a future cookie-based auth flow is added without revisiting this |
| Startup warnings instead of hard failure | App remains usable for local/dev without extra setup | Warnings can be missed if logs aren't monitored; misconfiguration is not physically prevented |
| Minimal `main.py` | Easy to read entry point | All route logic lives in `routes.py` |

## Security notes

- OpenAPI (`/docs`, `/redoc`) is disabled when `SPOON_ENV=production`.
- Unhandled exceptions never expose `str(exc)` to the client.
- API key enforcement is **not** in `main.py`; it is applied per-route via `require_api_key` in `routes.py`.
- Rate limiting is enabled by default (`SPOON_RATE_LIMIT_ENABLED=true`); set `SPOON_RATE_LIMIT_BACKEND=redis` for correctness across multiple workers/replicas.
- CORS is disabled by default; only enable it with an explicit, minimal origin allowlist via `SPOON_CORS_ALLOWED_ORIGINS`.
- Watch server logs at startup for `WARNING`/`CRITICAL` lines from `_warn_on_insecure_config()` — they call out the two most impactful misconfigurations (no API key, no token encryption).

## Extension guide

| Goal | Where to change |
| --- | --- |
| Add a new middleware | Register in `main.py` before or after existing middleware (mind LIFO order) |
| Change API prefix | Update `prefix=` in `include_router` and `RATE_LIMITS` keys in `security.py` |
| Add lifespan hooks (DB, Redis) | Use `@app.on_event("startup")` or FastAPI `lifespan` context manager |
| Widen/narrow CORS | Edit `SPOON_CORS_ALLOWED_ORIGINS` (env-only, no code change needed) or `allow_methods`/`allow_headers` in `main.py` for a code-level change |
| Health at root | Either add a route in `main.py` or keep `/api/v1/health` in `routes.py` |
| Structured JSON logging | Replace or extend `setup_logging()` in `app/logging.py` |
| Fail hard instead of warn | Replace the `logger.warning(...)` calls in `_warn_on_insecure_config()` with `raise RuntimeError(...)` if you want misconfiguration to prevent startup entirely |

## Related documentation

- [config.md](./config.md) — settings and production flag, including new `cors_allowed_origins`/`rate_limit_backend`/`trust_proxy_headers`
- [routes.md](./routes.md) — mounted router
- [logging.md](./logging.md) — middleware and log setup
- [core/security.md](./core/security.md) — rate limit middleware, API key auth
