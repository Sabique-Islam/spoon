# `app/logging.py`

**Source:** [`app/logging.py`](../../app/logging.py)  
**Lines:** 57

## Purpose

Configures application logging to stdout and provides middleware and helper functions for HTTP request timing, sync metrics, search timing, and audit events.

## Role in the stack

| Component | When it runs |
| --- | --- |
| `setup_logging()` | Once at import in `main.py` |
| `RequestLoggingMiddleware` | Every HTTP request/response |
| `log_sync` | After each sync in `routes.py` |
| `log_search` | After successful search |
| `log_audit` | OAuth connect/disconnect and sync completion |

All use the shared logger name `"spoon"`.

## Dependencies

| Import | Purpose |
| --- | --- |
| `logging`, `sys` | Handler to stdout |
| `time` | Request and operation duration |
| `Callable` | Middleware typing |
| `BaseHTTPMiddleware` | Starlette middleware base |
| `Request`, `Response` | ASGI request/response |

## Line-by-line reference

| Lines | Code | Behavior |
| --- | --- | --- |
| 1–8 | Imports | stdlib + Starlette middleware types |
| 10 | `logger = logging.getLogger("spoon")` | Application-wide logger |
| 13–20 | `setup_logging()` | StreamHandler on stdout, INFO level, idempotent handler attach |
| 14–16 | Formatter | `asctime levelname name message` |
| 18 | `setLevel(INFO)` | Default verbosity |
| 19–20 | Handler guard | Avoid duplicate handlers on reload |
| 23–35 | `RequestLoggingMiddleware` | Wraps each request |
| 25 | `perf_counter` start | High-resolution timer |
| 26 | `call_next` | Invokes route + inner middleware |
| 27–33 | Log line | `METHOD path -> status (X.Xms)` at INFO |
| 35 | Return response | Unmodified passthrough |
| 38–47 | `log_sync()` | Summary INFO + per-error ERROR lines |
| 39–45 | Summary | provider, document count, duration, error count |
| 46–47 | Loop | Each sync error logged at ERROR with provider |
| 50–51 | `log_search()` | Search duration only (query not logged) |
| 54–56 | `log_audit()` | Filters sensitive keys; INFO audit line |

## Log format examples

| Function | Example output |
| --- | --- |
| Middleware | `2026-07-03 12:00:00 INFO spoon GET /api/v1/health -> 200 (1.2ms)` |
| `log_sync` | `sync provider=notion documents=42 duration_ms=1523.4 errors=0` |
| `log_search` | `search duration_ms=89.3` |
| `log_audit` | `audit action=oauth_connect provider=slack` |

## Tradeoffs

| Choice | Benefit | Cost |
| --- | --- | --- |
| Plain text logs | Simple grep/journald | Not structured JSON for log aggregators |
| Single logger name | Consistent filtering | No per-module log levels |
| Search query not logged | Privacy | Harder to debug search issues |
| Audit field filter by key name | Reduces accidental secret logs | Heuristic only — nested secrets not filtered |
| Sync errors logged twice | Once raw in `log_sync`, sanitized to client | Verbose logs on large error lists |

## Security notes

- `log_audit` strips top-level fields named `token`, `secret`, `password` only.
- Sync errors in `log_sync` may contain sensitive URLs or tokens before client sanitization — protect log storage.
- Request logs include path but not headers (API keys not logged by this module).
- Consider log retention and access controls in production.

## Extension guide

1. **JSON logging:** Replace `Formatter` with a custom JSON formatter or use `python-json-logger`.
2. **Request ID:** Generate UUID in middleware, attach to `request.state`, include in all log calls.
3. **Log levels:** Use `DEBUG` for search queries in dev via env-driven level in `setup_logging`.
4. **Correlation:** Pass `request_id` into `log_sync` / `log_audit` from routes.
5. **PII redaction:** Extend `log_audit` with regex patterns similar to [core/errors.md](./core/errors.md).

## Related documentation

- [main.md](./main.md) — registers middleware and calls `setup_logging`
- [routes.md](./routes.md) — calls audit/sync/search log helpers
- [core/errors.md](./core/errors.md) — complementary client-side error redaction
