# `app/supermemory/search.py`

**Source:** [`app/supermemory/search.py`](../../app/supermemory/search.py)  
**Lines:** 16

## Purpose

Thin adapter that searches indexed documents in Supermemory scoped to Spoon's configured `container_tag`, returning raw result objects for the HTTP search API.

## Role in the stack

```
POST /api/v1/search  →  routes.search  →  search_documents  →  Supermemory SDK
```

Validation of `query` and `limit` happens in [models.md](../models.md) `SearchRequest` before this module runs.

## Dependencies

| Import | Purpose |
| --- | --- |
| `typing.Any` | Return type of results |
| `get_settings` | `container_tag` |
| `get_supermemory_client` | SDK singleton |

## Line-by-line reference

| Lines | Code | Behavior |
| --- | --- | --- |
| 1 | `from typing import Any` | Opaque results typing |
| 3–4 | Config and client imports | Settings + Supermemory factory |
| 7 | `search_documents` signature | `query: str`, `limit: int = 10` |
| 8 | `client = get_supermemory_client()` | Cached SDK client |
| 9 | `settings = get_settings()` | For container tag |
| 10–14 | `client.search.documents(...)` | SDK search call |
| 11 | `q=query` | User query string |
| 12 | `container_tags=[settings.container_tag]` | Isolate Spoon data in Supermemory |
| 13 | `limit=limit` | Max results (1–100 from API model) |
| 15 | `return response.results` | Pass through SDK result list/object |

## API parameters mapped to SDK

| Spoon input | SDK argument | Source |
| --- | --- | --- |
| `query` | `q` | Request body |
| `limit` | `limit` | Request body, default 10 |
| — | `container_tags` | `SPOON_CONTAINER_TAG` (default `spoon`) |

## Tradeoffs

| Choice | Benefit | Cost |
| --- | --- | --- |
| Return `response.results` only | Simple JSON serialization | Drops scores/metadata at top level if present on response object |
| Single container tag | Multi-tenant isolation by deployment | Cannot search across tags without code change |
| Sync function in async route | Simple call | Blocks event loop if SDK is sync (depends on SDK impl) |
| No caching | Fresh results | Repeated queries hit Supermemory every time |

## Security notes

- Search is scoped by `container_tag` — wrong tag in config exposes wrong corpus or empty results.
- Query text is not logged in [logging.md](../logging.md) `log_search` — good for privacy.
- Route returns 502 on any exception — avoid putting exception details in client response (handled in routes).
- API key required when `SPOON_API_KEY` set — search endpoint protected.

## Extension guide

1. **Filters:** Add metadata filters to SDK call if supported (e.g. by `source` field from ingest metadata).
2. **Typed results:** Map SDK results to Pydantic models before return; update `SearchResponse`.
3. **Async SDK:** If Supermemory adds async client, make `search_documents` async.
4. **Pagination:** Pass offset/cursor through to SDK when available.
5. **Hybrid search:** Combine multiple `container_tags` for staging vs production if needed.

## Related documentation

- [client.md](./client.md) — SDK factory
- [ingest.md](./ingest.md) — how documents enter the same container tag
- [routes.md](../routes.md) — HTTP wrapper and error handling
- [models.md](../models.md) — `SearchRequest` / `SearchResponse`
