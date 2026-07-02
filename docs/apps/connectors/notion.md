# `notion.py` — Notion Page Sync

## Purpose

`notion.py` syncs **Notion pages** into Spoon documents. It searches for all accessible pages, recursively fetches block children, converts blocks to plain text, and uploads the batch to Supermemory.

Authentication supports **Notion OAuth** or a static **integration API key** (`SPOON_NOTION_API_KEY`).

## Architecture Role

```
Notion OAuth / API key
        │
        ▼
NotionConnector.sync()
        │
        ├── _fetch_pages()              — POST /search (object=page)
        └── for each page:
                ├── _fetch_block_children()  — recursive blocks API
                ├── blocks_to_plain_text()
                └── page_to_document()
        │
        ▼
upload_documents(all documents)
        │
        ▼
Supermemory
```

| Component | Role |
|-----------|------|
| Block tree fetch | Depth-limited recursion via `max_block_depth` |
| Block types | Subset of Notion blocks converted to text |
| Search API | Discovers pages user/integration can access |

## Dependencies

| Import | Module | Usage |
|--------|--------|-------|
| `asyncio`, `logging` | stdlib | Retries, errors |
| `httpx` | third-party | Notion REST API |
| `get_notion_access_token`, `refresh_notion_token_if_needed` | `app.auth.notion_oauth` | Token resolution/refresh |
| `get_settings` | `app.config` | API version, depth, content length |
| `SyncResult` | `app.connectors.base` | Sync outcome |
| `Document` | `app.models` | Output model |
| `upload_documents` | `app.supermemory.ingest` | Batch upload |

## Line-Range Reference

| Lines | Section | Description |
|-------|---------|-------------|
| 1–3 | Imports | asyncio, logging, typing |
| 5 | httpx | HTTP client |
| 7–11 | App imports | auth, config, base, models, ingest |
| 13 | Logger | `"spoon"` |
| 15 | `NOTION_API_BASE` | `https://api.notion.com/v1` |
| 16–17 | Retry constants | Status codes, max retries |
| 20–26 | `extract_title` | Find title property on page |
| 29–30 | `rich_text_to_plain` | Join rich_text plain_text segments |
| 33–56 | `block_to_text` | Single block → plain string |
| 59–75 | `blocks_to_plain_text` | Recursive block tree flattening |
| 78–95 | `page_to_document` | Page + content → Document |
| 98–273 | `NotionConnector` | Connector class |

### `block_to_text` supported types (39–51)

| Block types |
|-------------|
| paragraph, heading_1/2/3, bulleted_list_item, numbered_list_item |
| to_do, quote, callout, toggle, code |

Unsupported block types return empty string (no table, image, embed text).

### `blocks_to_plain_text` (59–75)

| Lines | Logic |
|-------|-------|
| 60–62 | Stop if depth > max_block_depth |
| 64–68 | Append block text |
| 69–73 | Recurse into `children` if present |
| 75 | Join lines with newline |

### `NotionConnector` (98–273)

| Lines | Member | Description |
|-------|--------|-------------|
| 99 | `provider` | `"notion"` |
| 101–102 | `__init__` | Cache settings reference |
| 104–110 | `is_authenticated` | OAuth token or API key |
| 112–141 | `_request` | HTTP with Notion-Version header, retries |
| 143–182 | `_fetch_block_children` | Paginated + recursive children |
| 184–213 | `_fetch_pages` | Search API pagination |
| 215–221 | `_resolve_token` | get_notion_access_token |
| 223–273 | `sync` | Full sync pipeline |

### `_fetch_block_children` (143–182)

| Lines | Logic |
|-------|-------|
| 150–151 | Depth guard |
| 153–154 | Accumulator, cursor |
| 156–159 | page_size 100, start_cursor |
| 161–168 | GET /blocks/{id}/children |
| 171–176 | If has_children, recurse and attach |
| 178–180 | Pagination until not has_more |

### `_fetch_pages` (184–213)

| Lines | Logic |
|-------|-------|
| 187–188 | pages list, cursor |
| 191–196 | POST /search filter object=page |
| 198–206 | Request, 401 handling |
| 207 | Extend results |
| 209–211 | Pagination |

### `sync` (223–273)

| Lines | Logic |
|-------|-------|
| 225–229 | Resolve token |
| 232–252 | Fetch pages; 401 refresh retry |
| 254–264 | Per-page blocks + document build |
| 266–271 | upload_documents; error handling |
| 273 | Return result |

## Functions and Classes

### Constants

| Name | Purpose |
|------|---------|
| `NOTION_API_BASE` | Notion API v1 root |
| `RETRYABLE_STATUS` | 429, 5xx |
| `MAX_RETRIES` | 3 |

### Module functions

| Function | Input | Output |
|----------|-------|--------|
| `extract_title(page)` | Page dict | Title string or "Untitled" |
| `rich_text_to_plain(rich_text)` | Rich text array | Concatenated plain text |
| `block_to_text(block)` | Block dict | Text or "" |
| `blocks_to_plain_text(blocks, depth=0)` | Block list | Multiline plain text |
| `page_to_document(page, content)` | Page + text | Document |

### `NotionConnector`

| Method | Description |
|--------|-------------|
| `__init__()` | Stores settings |
| `is_authenticated()` | OAuth or API key |
| `_request(client, method, path, token, **kwargs)` | Authenticated API call |
| `_fetch_block_children(...)` | Recursive block tree |
| `_fetch_pages(...)` | All accessible pages |
| `_resolve_token()` | Token or ValueError |
| `sync()` | End-to-end sync |

## Tradeoffs

### Pros

| Benefit | Detail |
|---------|--------|
| Recursive blocks | Captures nested page content |
| Depth limit | Prevents runaway API calls on deep pages |
| Dual auth | OAuth for users, API key for internal |
| Token refresh path | 401 retry with refresh |
| Pure normalizers | Easy to unit test block conversion |

### Cons

| Limitation | Detail |
|------------|--------|
| Many block types ignored | Tables, databases, embeds skipped |
| N+1 API pattern | One children fetch tree per page |
| No incremental sync | Full search every run |
| Flat text output | No heading hierarchy preserved |
| Database rows not synced | Only `object=page` in search filter |

### Alternatives

| Alternative | When |
|-------------|------|
| Notion export API | Bulk markdown export |
| Database query endpoint | Sync database rows as docs |
| Block type handlers | Richer content (tables → markdown) |
| Incremental via last_edited_time | Large workspaces |

## Security and Resource Notes

| Topic | Detail |
|-------|--------|
| Notion-Version header | From `settings.notion_version` |
| API key / OAuth | Stored per auth module |
| max_block_depth | Default 10 — limits recursion |
| max_content_length | Truncates page content |
| Timeout | 30s per request |
| Access scope | Limited to integration-shared pages |

## Extension Guide

### Support more block types

Extend `block_to_text`:

```python
if block_type == "table":
    rows = data.get("children", [])  # requires expanded fetch
    ...
```

Note: tables may need additional API calls for row cells.

### Sync databases

Add `_fetch_databases` using search filter `object=database`, then query each database with `/databases/{id}/query`.

### Incremental sync

Filter search payload with `last_edited_time` filter (Notion API filter syntax).

### Respect sync limits

Slice `documents` before `upload_documents` or switch to `upload_document_batch`.

Tests: `tests/test_sync.py`, `tests/test_auth_fallback.py`
