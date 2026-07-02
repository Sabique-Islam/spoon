# `app/http/retry_client.py`

**Source:** [`app/http/retry_client.py`](../../app/http/retry_client.py)  
**Lines:** 29

## Purpose

Async HTTP helper that retries requests against upstream APIs when responses indicate transient failures (rate limits and 5xx errors), using exponential backoff derived from `Retry-After` or `2**attempt`.

## Role in the stack

Used by connectors and OAuth modules that share an `httpx.AsyncClient` and need resilient outbound calls without duplicating retry logic.

## Dependencies

| Import | Purpose |
| --- | --- |
| `asyncio` | Sleep between retries |
| `typing.Any` | `**kwargs` passthrough to httpx |
| `httpx` | Async HTTP client |

## Constants

| Name | Value | Meaning |
| --- | --- | --- |
| `RETRYABLE_STATUS` | `{429, 500, 502, 503, 504}` | Status codes that trigger retry |
| `MAX_RETRIES` | `3` | Total attempts (initial + 2 retries) |

## Line-by-line reference

| Lines | Code | Behavior |
| --- | --- | --- |
| 1 | `import asyncio` | Backoff sleep |
| 2 | `from typing import Any` | Kwargs typing |
| 4 | `import httpx` | HTTP client library |
| 6 | `RETRYABLE_STATUS` | Frozen set of retryable HTTP statuses |
| 7 | `MAX_RETRIES = 3` | Loop upper bound |
| 10–17 | Function signature | Async; requires injected `AsyncClient` |
| 11–12 | `client`, `method`, `url` | Required positional args |
| 15 | `timeout=120.0` | Default 120s per attempt |
| 16 | `**kwargs` | Headers, json, params, etc. passed to httpx |
| 18 | `last_response` | Tracks final response for return |
| 19 | `for attempt in range(MAX_RETRIES)` | Attempts 0, 1, 2 |
| 20 | `client.request(...)` | Single HTTP round trip |
| 21 | Store response | Save to `last_response` |
| 22–23 | Success path | Non-retryable status → return immediately |
| 24 | Backoff | `Retry-After` header int or `2**attempt` seconds |
| 25 | `asyncio.sleep(retry_after)` | Wait before next attempt |
| 27–28 | Exhausted retries | Assert and return last retryable response |

## Retry timeline example

| Attempt | On 503 | Sleep before next |
| --- | --- | --- |
| 0 | 503 | `Retry-After` or 1s (`2**0`) |
| 1 | 503 | `Retry-After` or 2s |
| 2 | 503 | Return 503 (no further retry) |

## Tradeoffs

| Choice | Benefit | Cost |
| --- | --- | --- |
| Shared helper | DRY across connectors | One policy fits all providers |
| Retry 429 | Handles rate limits | May amplify quota usage |
| No jitter | Simple | Thundering herd on recovery |
| Returns last error response | Caller handles status | Does not raise on exhausted 5xx |
| 120s default timeout | Long polls OK | Hung requests block worker |

## Security notes

- Retries replay identical requests — unsafe for non-idempotent POST unless upstream is designed for it.
- Do not log full `kwargs` at debug level if they contain Authorization headers.
- `Retry-After` is cast with `int()` — malformed header raises `ValueError` (uncaught).

## Extension guide

1. **Idempotency keys:** Accept optional header factory for retry-safe POSTs.
2. **Jitter:** Add `random.uniform(0, retry_after)` to sleep.
3. **Configurable retries:** Pass `max_retries` or read from settings.
4. **Raise on failure:** Optional flag to raise `httpx.HTTPStatusError` after last attempt.
5. **Network errors:** Catch `httpx.TransportError` and retry separately from HTTP status.
6. **Metrics:** Emit counter `http_retries_total{status=503}` for observability.

## Related documentation

- Connectors under [connectors/](../connectors/) — primary consumers
- [config.md](../config.md) — sync timeouts and limits at application level
