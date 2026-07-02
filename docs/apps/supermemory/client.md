# `app/supermemory/client.py`

**Source:** [`app/supermemory/client.py`](../../app/supermemory/client.py)  
**Lines:** 12

## Purpose

Provides a cached singleton factory for the official Supermemory Python SDK client, configured with the API key from application settings.

## Role in the stack

| Consumer | Usage |
| --- | --- |
| [search.py](./search.md) | `client.search.documents(...)` |
| [ingest.py](./ingest.md) | `client.documents.add`, `upload_file`, `batch_add` |

All Supermemory traffic should go through `get_supermemory_client()` to share one SDK instance and API key binding.

## Dependencies

| Import | Module | Purpose |
| --- | --- | --- |
| `lru_cache` | `functools` | Process-wide client singleton |
| `Supermemory` | `supermemory` | Official SDK client class |
| `get_settings` | `app.config` | `supermemory_api_key` |

## Line-by-line reference

| Lines | Code | Behavior |
| --- | --- | --- |
| 1 | `from functools import lru_cache` | Cache decorator for factory |
| 3 | `from supermemory import Supermemory` | SDK entry point |
| 5 | `from app.config import get_settings` | Settings accessor |
| 8–9 | `@lru_cache` + def | Cached zero-arg factory |
| 10 | `settings = get_settings()` | Load env/config |
| 11 | `return Supermemory(api_key=...)` | Construct SDK client with key |

## Tradeoffs

| Choice | Benefit | Cost |
| --- | --- | --- |
| `@lru_cache` | Single client, connection reuse | API key change requires process restart + `cache_clear()` |
| Thin wrapper | Minimal indirection | No custom timeouts/retries at client level |
| Required API key in settings | Fail fast at Settings init | App won't start without key even if search unused |

## Security notes

- `supermemory_api_key` is required (`SPOON_SUPERMEMORY_API_KEY`) — treat as secret.
- SDK may log requests in debug mode — disable verbose SDK logging in production.
- Client is shared across requests — no per-user Supermemory isolation except via `container_tag`.

## Extension guide

1. **Custom base URL:** Pass additional SDK constructor args if Supermemory supports staging endpoints.
2. **Testing:** Mock `get_supermemory_client` or call `get_supermemory_client.cache_clear()` and patch settings.
3. **Lazy init:** Remove `@lru_cache` if you need per-request clients ( uncommon ).
4. **Health check:** Add `verify_supermemory()` that performs a minimal API call on startup.
5. **Multiple containers:** Factory could accept `container_tag` parameter — today tag is passed per call in search/ingest.

## Related documentation

- [config.md](../config.md) — `supermemory_api_key`, `container_tag`
- [search.md](./search.md) — document search
- [ingest.md](./ingest.md) — document upload
