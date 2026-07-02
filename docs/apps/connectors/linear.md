# `linear.py` — Linear Issue and Project Sync

## Purpose

`linear.py` syncs **Linear issues** and **projects** into Spoon documents via the Linear GraphQL API. It paginates through all issues and projects, converts each record to a normalized `Document`, and uploads the full batch to Supermemory.

Authentication uses a static API key (`SPOON_LINEAR_API_KEY`), not OAuth.

## Architecture Role

```
SPOON_LINEAR_API_KEY
        │
        ▼
LinearConnector.sync()
        │
        ├── _fetch_paginated(ISSUES_QUERY)  → issue_to_document()
        └── _fetch_paginated(PROJECTS_QUERY) → project_to_document()
        │
        ▼
upload_documents(all documents)
        │
        ▼
Supermemory
```

| Stage | Responsibility |
|-------|----------------|
| GraphQL queries | Fetch issues/projects with metadata |
| Normalizers | `issue_to_document`, `project_to_document` |
| HTTP layer | `_graphql` with retries, `_fetch_paginated` |
| Upload | Single batch via `upload_documents` (not `upload_document_batch`) |

## Dependencies

| Import | Module | Usage |
|--------|--------|-------|
| `asyncio`, `logging` | stdlib | Retry backoff, error logging |
| `httpx` | third-party | Async HTTP to Linear GraphQL |
| `get_settings` | `app.config` | API key, content length |
| `SyncResult` | `app.connectors.base` | Sync outcome |
| `Document` | `app.models` | Output model |
| `upload_documents` | `app.supermemory.ingest` | Batch upload |

## Line-Range Reference

| Lines | Section | Description |
|-------|---------|-------------|
| 1–4 | Imports | asyncio, logging, typing |
| 6 | httpx | Async HTTP client |
| 8–11 | App imports | config, base, models, ingest |
| 13 | Logger | `"spoon"` logger |
| 15 | `LINEAR_API_URL` | `https://api.linear.app/graphql` |
| 16 | `RETRYABLE_STATUS` | `{429, 500, 502, 503, 504}` |
| 17 | `MAX_RETRIES` | `3` |
| 18 | `PAGE_SIZE` | `50` items per GraphQL page |
| 20–44 | `ISSUES_QUERY` | GraphQL query for paginated issues |
| 46–72 | `PROJECTS_QUERY` | GraphQL query for paginated projects |
| 75–76 | `_truncate` | Local content length helper |
| 79–128 | `issue_to_document` | Issue dict → `Document` |
| 131–185 | `project_to_document` | Project dict → `Document` |
| 188–306 | `LinearConnector` | Main connector class |

### `LinearConnector` detail

| Lines | Member | Description |
|-------|--------|-------------|
| 189 | `provider` | `"linear"` |
| 191–192 | `is_authenticated` | Checks `settings.linear_api_key` |
| 194–236 | `_graphql` | POST query with auth, retries, error handling |
| 238–261 | `_fetch_paginated` | Cursor pagination over a connection |
| 263–306 | `sync` | Orchestrates fetch, convert, upload |

### `issue_to_document` detail (79–128)

| Lines | Logic |
|-------|-------|
| 80–84 | Extract labels, state, team, assignee, project |
| 86–88 | Build content from description |
| 90–102 | Append structured detail lines |
| 104 | Truncate joined content |
| 106–107 | Identifier and title |
| 109–128 | Build `Document` with metadata |

### `project_to_document` detail (131–185)

| Lines | Logic |
|-------|-------|
| 132–137 | Teams, lead, status |
| 139–143 | Content from `content` or `description` |
| 145–160 | Detail lines including progress/dates |
| 162–185 | Build `Document` |

### `_graphql` detail (194–236)

| Lines | Logic |
|-------|-------|
| 200–207 | Auth header, JSON content type |
| 209–220 | Retry loop with exponential backoff |
| 222–227 | 401 → `HTTPStatusError`; other errors via `raise_for_status` |
| 229–234 | GraphQL-level errors → `ValueError` |
| 236 | Return `data` payload |

## Functions and Classes

### Constants

| Name | Value | Purpose |
|------|-------|---------|
| `LINEAR_API_URL` | Linear GraphQL endpoint | Single API URL |
| `RETRYABLE_STATUS` | 429, 5xx | Transient HTTP codes |
| `MAX_RETRIES` | 3 | Retry attempts |
| `PAGE_SIZE` | 50 | GraphQL `first` argument |

### Module functions

| Function | Input | Output |
|----------|-------|--------|
| `_truncate(content)` | `str` | Truncated `str` |
| `issue_to_document(issue)` | Issue dict | `Document` |
| `project_to_document(project)` | Project dict | `Document` |

### `LinearConnector`

| Method | Description |
|--------|-------------|
| `is_authenticated()` | True if API key set |
| `_graphql(client, query, variables)` | Execute GraphQL with retries |
| `_fetch_paginated(client, query, connection_name)` | Accumulate all nodes |
| `sync()` | Full sync pipeline |

## Tradeoffs

### Pros

| Benefit | Detail |
|---------|--------|
| Single batch upload | Efficient for moderate dataset sizes |
| Rich metadata | Issues include team, labels, assignee, project |
| Retry on rate limits | Handles 429/5xx with backoff |
| Pure API key auth | Simple deployment, no token refresh |

### Cons

| Limitation | Detail |
|------------|--------|
| No incremental sync | Fetches all issues/projects every run |
| No document limit | Unlike Gmail/Slack, does not use `upload_document_batch` quota during fetch |
| Local `_truncate` | Duplicates `text.truncate` |
| GraphQL errors abort connection | One failed connection type still allows partial docs if other succeeds |

### Alternatives

| Alternative | When |
|-------------|------|
| Incremental sync via `updatedAt` filter | Large workspaces |
| `upload_document_batch` | Enforce global sync limits consistently |
| OAuth instead of API key | User-scoped access |
| Sync comments/sub-issues | Richer context for search |

## Security and Resource Notes

| Topic | Detail |
|-------|--------|
| API key | Sent as `Authorization` header raw value (Linear convention) |
| Env var | `SPOON_LINEAR_API_KEY` |
| Timeout | 30s per GraphQL request |
| Memory | All documents held in memory before upload |
| PII | Issue descriptions may contain sensitive text; stored in Supermemory |

## Extension Guide

### Add another Linear object type (e.g. cycles)

1. Define a new GraphQL query constant with pagination fields.
2. Add `cycle_to_document(cycle: dict) -> Document`.
3. Extend `fetchers` list in `sync()`:

```python
fetchers = [
    ("issues", ISSUES_QUERY, "issues", issue_to_document),
    ("projects", PROJECTS_QUERY, "projects", project_to_document),
    ("cycles", CYCLES_QUERY, "cycles", cycle_to_document),
]
```

### Respect sync limits

Replace final `upload_documents(documents)` with slicing + `upload_document_batch` or cap documents before upload.

### Test normalizers

`issue_to_document` and `project_to_document` are pure functions — unit test with fixture JSON without HTTP.

See `tests/test_linear_normalize.py` for patterns.
