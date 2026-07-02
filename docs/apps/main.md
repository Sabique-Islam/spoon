# `app/main.py`

**Source:** [`app/main.py`](../../app/main.py)  
**Lines:** 30

## Purpose

Application entry point for the Spoon FastAPI service. Wires configuration, logging, middleware, API routes, and a global exception handler into a single ASGI app object consumed by Uvicorn (or any ASGI server).

## Role in the stack

| Layer | Responsibility |
| --- | --- |
| Bootstrap | Calls `setup_logging()` before any request handling |
| Configuration | Loads cached `Settings` via `get_settings()` |
| HTTP surface | Mounts `/api/v1` router; disables OpenAPI UI in production |
| Cross-cutting | Rate limiting and request logging middleware |
| Safety net | Catches unhandled exceptions and returns generic 500 JSON |

## Dependencies

| Import | Module | Usage |
| --- | --- | --- |
| `logging` | stdlib | Module-level logger |
| `FastAPI`, `Request` | `fastapi` | App factory and exception handler typing |
| `JSONResponse` | `fastapi.responses` | Error response body |
| `get_settings` | `app.config` | Environment-driven settings |
| `RateLimitMiddleware` | `app.core.security` | Per-path rate limits |
| `RequestLoggingMiddleware`, `setup_logging` | `app.logging` | Structured request timing logs |
| `router` | `app.routes` | All REST endpoints |

## Line-by-line reference

| Lines | Code | Behavior |
| --- | --- | --- |
| 1 | `import logging` | Standard logging module for unhandled errors |
| 3–4 | FastAPI imports | App class and request type for exception handler |
| 5 | `JSONResponse` | JSON error payloads |
| 7–9 | App imports | Config, security, logging, routes |
| 11 | `setup_logging()` | Configures `spoon` logger to stdout before app creation |
| 12 | `logger = logging.getLogger("spoon")` | Shared logger name used across the app |
| 14 | `settings = get_settings()` | Loads `.env` / env vars once at import (cached) |
| 15–20 | `FastAPI(...)` | Creates app; hides `/docs` and `/redoc` when `env=production` |
| 21 | `add_middleware(RateLimitMiddleware)` | Outermost added = runs first on request (Starlette LIFO) |
| 22 | `add_middleware(RequestLoggingMiddleware)` | Logs method, path, status, duration after inner handlers |
| 23 | `include_router(router, prefix="/api/v1")` | Mounts all routes under `/api/v1` |
| 26–29 | `@app.exception_handler(Exception)` | Logs full traceback; client sees `"Internal server error"` only |

## Middleware order

Starlette applies middleware in reverse registration order:

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
| Minimal `main.py` | Easy to read entry point | All route logic lives in `routes.py` |

## Security notes

- OpenAPI (`/docs`, `/redoc`) is disabled when `SPOON_ENV=production`.
- Unhandled exceptions never expose `str(exc)` to the client.
- API key enforcement is **not** in `main.py`; it is applied per-route via `require_api_key` in `routes.py`.
- Rate limiting is enabled by default (`SPOON_RATE_LIMIT_ENABLED=true`).

## Extension guide

| Goal | Where to change |
| --- | --- |
| Add a new middleware | Register in `main.py` before or after existing middleware (mind LIFO order) |
| Change API prefix | Update `prefix=` in `include_router` and `RATE_LIMITS` keys in `security.py` |
| Add lifespan hooks (DB, Redis) | Use `@app.on_event("startup")` or FastAPI `lifespan` context manager |
| CORS | Add `CORSMiddleware` here with explicit allowed origins |
| Health at root | Either add a route in `main.py` or keep `/api/v1/health` in `routes.py` |
| Structured JSON logging | Replace or extend `setup_logging()` in `app/logging.py` |

## Related documentation

- [config.md](./config.md) — settings and production flag
- [routes.md](./routes.md) — mounted router
- [logging.md](./logging.md) — middleware and log setup
- [core/security.md](./core/security.md) — rate limit middleware
