# `app/models.py`

**Source:** [`app/models.py`](../../app/models.py)  
**Lines:** 40

## Purpose

Pydantic v2 models defining the HTTP request/response schemas and the canonical in-memory `Document` shape used by connectors and Supermemory ingest.

## Role in the stack

| Model | Used by |
| --- | --- |
| `Document` | Connectors, `supermemory/ingest.py` |
| `SyncResponse` | Sync routes, connector return values |
| `SearchRequest` / `SearchResponse` | `POST /api/v1/search` |
| `ErrorResponse` | Implicit error shape (routes use `detail={"error": ...}`) |
| `HealthResponse` | `GET /api/v1/health` |
| `ProvidersResponse` | `GET /api/v1/providers` |

## Dependencies

| Import | Purpose |
| --- | --- |
| `typing.Any`, `Literal` | `Literal` imported but unused in current file |
| `pydantic.BaseModel`, `Field` | Validation and OpenAPI schema generation |

## Line-by-line reference

| Lines | Code | Behavior |
| --- | --- | --- |
| 1 | `from typing import Any, Literal` | Type hints; `Literal` currently unused |
| 3–4 | Pydantic imports | Model base and field helpers |
| 6–12 | `class Document` | Canonical synced item before Supermemory upload |
| 7 | `id: str` | Stable source-specific identifier |
| 8 | `source: str` | Provider name (e.g. `gmail`, `notion`) |
| 9 | `title: str` | Human-readable title |
| 10 | `content: str` | Searchable text body |
| 11 | `url: str` | Link back to source resource |
| 12 | `metadata: dict[str, Any]` | Extra key-value data; defaults to `{}` |
| 15–18 | `class SyncResponse` | API response after sync |
| 16 | `provider: str` | Which connector ran |
| 17 | `documents_processed: int` | Count of documents uploaded/indexed |
| 18 | `errors: list[str]` | Non-fatal per-item errors; sanitized in routes |
| 21–23 | `class SearchRequest` | Search API body |
| 22 | `query: str` | 1–1000 characters required |
| 23 | `limit: int` | Default 10, clamped 1–100 |
| 26–27 | `class SearchResponse` | Wrapper for Supermemory results |
| 27 | `results: Any` | Opaque pass-through from Supermemory SDK |
| 30–31 | `class ErrorResponse` | Simple `{ "error": "..." }` schema |
| 34–35 | `class HealthResponse` | Liveness probe; default `status="ok"` |
| 38–39 | `class ProvidersResponse` | List of supported connector names |

## Field constraints summary

| Model | Field | Constraint |
| --- | --- | --- |
| `SearchRequest` | `query` | `min_length=1`, `max_length=1000` |
| `SearchRequest` | `limit` | `ge=1`, `le=100`, default `10` |
| `Document` | `metadata` | Empty dict if omitted |
| `SyncResponse` | `errors` | Empty list if omitted |

## Tradeoffs

| Choice | Benefit | Cost |
| --- | --- | --- |
| `SearchResponse.results: Any` | SDK result shape can evolve without model changes | No OpenAPI detail for result items |
| Flat `Document` model | Easy connector mapping | No nested blocks/attachments in type system |
| `metadata` as open dict | Flexible per-provider fields | No schema validation on metadata keys |
| Separate API models vs `Document` | Clear HTTP contract | Some duplication with ingest payloads |

## Security notes

- `SearchRequest.query` length cap reduces abuse and oversized payloads.
- `SyncResponse.errors` are sanitized in routes via `sanitize_sync_errors` before return.
- `Document.content` is not truncated at model level; connectors respect `max_content_length` from config.
- Do not put secrets in `Document.metadata`; values may flow to Supermemory and logs.

## Extension guide

1. **Tighten search results:** Replace `results: Any` with a typed list model matching Supermemory response fields.
2. **Add pagination:** Extend `SearchRequest` with `offset` or cursor; update `routes.py` and `search.py`.
3. **Provider-specific metadata:** Use `TypedDict` or nested Pydantic models per `source` if validation is needed.
4. **OpenAPI errors:** Wire `ErrorResponse` as `responses={400: {"model": ErrorResponse}}` on routes.
5. **New endpoint schema:** Add models here first, then import in `routes.py` with `response_model=`.

## Related documentation

- [routes.md](./routes.md) — consumes all response/request models
- [supermemory/ingest.md](./supermemory/ingest.md) — maps `Document` to Supermemory payloads
- [core/errors.md](./core/errors.md) — sanitizes `SyncResponse.errors`
