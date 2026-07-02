# `base.py` — Connector Foundation

## Purpose

`base.py` defines the shared contract and utilities every Spoon connector uses during sync. It provides:

- A **`SyncResult`** dataclass for tracking progress and collecting errors during a sync run.
- An **`upload_document_batch`** helper that respects per-sync document limits before sending data to Supermemory.
- A **`Connector`** protocol that all provider implementations must satisfy.

This module is the glue between individual provider connectors and the Supermemory ingest pipeline.

## Architecture Role

```
┌─────────────────┐     implements      ┌──────────────────┐
│  registry.py    │ ──────────────────► │ Connector (Protocol)│
│  (factory)      │                     └────────┬─────────┘
└─────────────────┘                              │
                                                 │ sync() → SyncResult
┌─────────────────┐                              │
│ notion, slack,  │ ─────────────────────────────┘
│ gmail, etc.     │
└────────┬────────┘
         │ uses SyncResult, upload_document_batch
         ▼
┌─────────────────┐
│ supermemory/    │
│ ingest.py       │
└─────────────────┘
```

| Layer | Responsibility |
|-------|----------------|
| `Connector` protocol | Defines `provider`, `sync()`, `is_authenticated()` |
| `SyncResult` | Accumulates `documents_processed` and capped error list |
| `upload_document_batch` | Enforces `max_documents_per_sync` before upload |

Connectors that process items one-at-a-time (Gmail, Outlook, Slack channels) call `upload_document_batch` per document. Connectors that batch at the end (Linear, Notion) call `upload_documents` directly from `supermemory.ingest`.

## Dependencies

| Import | Module | Usage |
|--------|--------|-------|
| `dataclass`, `field` | `dataclasses` | `SyncResult` definition |
| `Protocol` | `typing` | Structural typing for `Connector` |
| `get_settings` | `app.config` | Read `max_documents_per_sync`, `max_content_length` |
| `truncate` | `app.connectors.text` | Content length limiting via `SyncResult.truncate` |
| `Document` | `app.models` | Typed document model passed to ingest |
| `upload_documents` | `app.supermemory.ingest` | Batch upload to Supermemory |

## Line-Range Reference

| Lines | Section | Description |
|-------|---------|-------------|
| 1–2 | Imports | Standard library typing + dataclass imports |
| 4–7 | App imports | Settings, text utils, models, ingest |
| 9 | Constant | `_MAX_SYNC_ERRORS = 50` — hard cap on stored error messages |
| 12–16 | `SyncResult` dataclass | Fields: `documents_processed` (int), `errors` (list) |
| 17–19 | `SyncResult.add_error` | Appends error only if under `_MAX_SYNC_ERRORS` |
| 21–23 | `SyncResult.can_add_documents` | Checks remaining quota against settings |
| 25–26 | `SyncResult.truncate` | Delegates to `text.truncate` |
| 29–43 | `upload_document_batch` | Slices batch to remaining quota, uploads, records count |
| 46–51 | `Connector` protocol | Interface: `provider`, `async sync()`, `is_authenticated()` |

## Functions and Classes

### `_MAX_SYNC_ERRORS` (constant)

| Property | Value |
|----------|-------|
| Value | `50` |
| Scope | Module-private |
| Purpose | Prevents unbounded error list growth during large failed syncs |

### `SyncResult`

| Member | Type | Description |
|--------|------|-------------|
| `documents_processed` | `int` | Count of documents successfully uploaded this sync |
| `errors` | `list[str]` | Human-readable error messages (max 50) |
| `add_error(message)` | method | Append error if under cap |
| `can_add_documents(count=1)` | method | Returns `True` if adding `count` docs stays within limit |
| `truncate(content)` | method | Truncate string to `max_content_length` |

### `upload_document_batch(documents, result)`

| Parameter | Type | Description |
|-----------|------|-------------|
| `documents` | `list[Document]` | Documents to upload |
| `result` | `SyncResult` | Mutated in place |

**Behavior:**

1. No-op if `documents` is empty.
2. Computes `remaining = max_documents_per_sync - result.documents_processed`.
3. If `remaining <= 0`, adds error and returns.
4. Uploads `documents[:remaining]` via `upload_documents`.
5. Increments `result.documents_processed`.
6. If input was truncated, adds a truncation error message.

### `Connector` (Protocol)

| Member | Signature | Description |
|--------|-----------|-------------|
| `provider` | `str` | Provider key (e.g. `"slack"`) |
| `sync` | `async () -> SyncResult` | Fetch, normalize, upload |
| `is_authenticated` | `() -> bool` | Whether credentials are configured |

## Tradeoffs

### Pros

| Benefit | Detail |
|---------|--------|
| Protocol over ABC | Connectors need not inherit; duck typing keeps modules decoupled |
| Centralized quota enforcement | `upload_document_batch` prevents runaway Supermemory usage |
| Capped errors | Avoids memory blow-up when thousands of items fail |
| Shared truncate path | Consistent content length limits across connectors |

### Cons

| Limitation | Detail |
|------------|--------|
| Inconsistent upload patterns | Some connectors use `upload_document_batch`, others call `upload_documents` directly |
| Error cap is silent | Errors beyond 50 are dropped without notification |
| No partial retry | Batch upload is all-or-nothing per call |
| Protocol not runtime-checked | Missing methods only fail at call time |

### Alternatives

| Alternative | When to consider |
|-------------|------------------|
| Abstract base class with shared HTTP/retry logic | If many connectors duplicate retry code |
| Streaming upload iterator | For very large syncs to avoid holding all docs in memory |
| Structured error types | If callers need machine-readable error codes |
| Unified upload helper | Force all connectors through one upload path with consistent limits |

## Security and Resource Notes

| Topic | Detail |
|-------|--------|
| Document quota | `max_documents_per_sync` (default 5000) limits Supermemory ingest per run |
| Content length | `SyncResult.truncate` uses `max_content_length` (default 100,000 chars) |
| Error messages | May contain provider API error text; avoid logging secrets |
| No credential handling | Authentication lives in each connector and auth modules |

## Extension Guide

### Adding a new connector

1. Create `app/connectors/myprovider.py` with a class that sets `provider = "myprovider"`.
2. Implement `is_authenticated()` checking your auth source.
3. Implement `async def sync(self) -> SyncResult` returning a populated `SyncResult`.
4. Use `upload_document_batch([doc], result)` for incremental uploads, or build a list and call `upload_documents` at the end.
5. Register in `registry.py` under `CONNECTORS`.

### Example skeleton

```python
from app.connectors.base import SyncResult, upload_document_batch
from app.models import Document

class MyProviderConnector:
    provider = "myprovider"

    def is_authenticated(self) -> bool:
        return bool(get_settings().myprovider_api_key)

    async def sync(self) -> SyncResult:
        result = SyncResult()
        if not self.is_authenticated():
            result.add_error("Not authenticated")
            return result
        doc = Document(id="...", source="myprovider", title="...", content="...", url="...")
        upload_document_batch([doc], result)
        return result
```

### Customizing error handling

Override nothing — call `result.add_error("message")` for recoverable failures. Fatal auth failures typically append to `result.errors` and return early.
