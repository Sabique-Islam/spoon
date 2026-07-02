# `gmail.py` — Gmail Email Sync

## Purpose

`gmail.py` syncs **Gmail messages** into Spoon documents using the Gmail REST API. It lists message IDs matching a query, fetches full message payloads, extracts plain/HTML bodies, and uploads each email as a separate document with incremental quota enforcement.

Authentication reuses **Google Drive OAuth** or a **service account** (same token as GDrive).

## Architecture Role

```
Google OAuth / Service Account (gdrive token store)
        │
        ▼
GmailConnector.sync()
        │
        ├── _fetch_message_ids()  — paginated list
        └── for each id: _fetch_message() → message_to_document()
        │
        ▼
upload_document_batch([doc], result)  — per message
        │
        ▼
Supermemory
```

| Component | Role |
|-----------|------|
| `LIST_QUERY` | Gmail search: all mail except spam/trash |
| `_list_query()` | Adds date filter from `sync_since_days` |
| `message_to_document` | MIME tree → structured email text |
| `upload_document_batch` | Respects `max_documents_per_sync` |

## Dependencies

| Import | Module | Usage |
|--------|--------|-------|
| `asyncio`, `base64`, `logging` | stdlib | Retries, body decode, errors |
| `datetime`, `timedelta`, `timezone` | stdlib | Date filter for sync window |
| `httpx` | third-party | Gmail API HTTP |
| `refresh_gdrive_token_if_needed` | `app.auth.gdrive_oauth` | OAuth token refresh |
| `has_service_account_fallback`, `service_account_token` | `app.auth.google_service_account` | SA auth |
| `get_provider_token` | `app.auth.store` | Check stored tokens |
| `get_settings` | `app.config` | Limits, sync window |
| `SyncResult`, `upload_document_batch` | `app.connectors.base` | Sync utilities |
| `html_to_text`, `truncate` | `app.connectors.text` | Body normalization |
| `Document` | `app.models` | Output model |

## Line-Range Reference

| Lines | Section | Description |
|-------|---------|-------------|
| 1–5 | Imports | stdlib |
| 7 | httpx | Async client |
| 9–18 | Auth & connector imports | gdrive oauth, SA, store, base, text, models |
| 20 | Logger | `"spoon"` |
| 22 | `GMAIL_API_BASE` | `https://gmail.googleapis.com/gmail/v1` |
| 23–25 | Retry/pagination constants | Status codes, retries, page size |
| 26 | `LIST_QUERY` | Base Gmail query string |
| 29–35 | `_list_query` | Append `after:YYYY/MM/DD` if configured |
| 38–39 | `_truncate` | Delegates to `text.truncate` |
| 42–44 | `_decode_body` | URL-safe base64 decode |
| 47–48 | `_html_to_text` | Wrapper for `html_to_text` |
| 51–56 | `_get_header` | Case-insensitive header lookup |
| 59–80 | `_extract_body` | Recursive MIME multipart walker |
| 83–130 | `message_to_document` | Message JSON → `Document` |
| 133–296 | `GmailConnector` | Connector class |

### `_extract_body` (59–80)

| Lines | Logic |
|-------|-------|
| 60–62 | Read mimeType and body.data |
| 64–69 | Single-part plain or HTML |
| 71–79 | Recurse into `parts`, join plain and HTML |
| 80 | Return `(plain, html)` tuple |

### `message_to_document` (83–130)

| Lines | Logic |
|-------|-------|
| 84–86 | Require message id |
| 88–94 | Parse Subject, From, To, Cc, Date headers |
| 96–99 | Body: plain > html_to_text > snippet; skip if empty |
| 101–110 | Format header block + body |
| 112–129 | Build `Document` with metadata |

### `GmailConnector` (133–296)

| Lines | Member | Description |
|-------|--------|-------------|
| 134 | `provider` | `"gmail"` |
| 136–140 | `is_authenticated` | gdrive token or service account |
| 142–155 | `_resolve_token` | OAuth refresh, then SA |
| 157–179 | `_request` | Bearer auth, retry on 429/5xx |
| 181–218 | `_fetch_message_ids` | Paginated messages.list |
| 220–238 | `_fetch_message` | messages.get format=full |
| 240–296 | `sync` | Token, list, fetch, upload loop |

### `sync` flow (240–296)

| Lines | Step |
|-------|------|
| 241–247 | Resolve token or error |
| 249–276 | Fetch message IDs; 401 retry with refresh |
| 278–280 | Pre-slice IDs to max_documents_per_sync |
| 282–294 | Per-message fetch, convert, upload |
| 296 | Return result |

## Functions and Classes

### Constants

| Name | Value |
|------|-------|
| `GMAIL_API_BASE` | Gmail v1 API root |
| `RETRYABLE_STATUS` | 429, 500, 502, 503, 504 |
| `MAX_RETRIES` | 3 |
| `PAGE_SIZE` | 100 |
| `LIST_QUERY` | `in:anywhere -in:spam -in:trash` |

### Module functions

| Function | Purpose |
|----------|---------|
| `_list_query()` | Query with optional date window |
| `_decode_body(data)` | Base64url → UTF-8 string |
| `_get_header(headers, name)` | Header value by name |
| `_extract_body(payload)` | MIME tree traversal |
| `message_to_document(message)` | Full message → Document |

### `GmailConnector`

| Method | Description |
|--------|-------------|
| `is_authenticated()` | Stored gdrive token or SA |
| `_resolve_token()` | Async token resolution |
| `_request(...)` | HTTP with retries (120s timeout) |
| `_fetch_message_ids(...)` | All matching message IDs |
| `_fetch_message(...)` | Single full message |
| `sync()` | End-to-end sync |

## Tradeoffs

### Pros

| Benefit | Detail |
|---------|--------|
| Incremental upload | One doc at a time with quota checks |
| Shared Google auth | No separate Gmail OAuth app |
| Date window | `sync_since_days` limits historical mail |
| MIME-aware bodies | Prefers plain text, falls back to HTML |
| 401 recovery | Retries list after token refresh |

### Cons

| Limitation | Detail |
|------------|--------|
| N+1 API calls | One get per message (slow for large mailboxes) |
| Pre-slice IDs only | Fetches full ID list before truncating |
| No thread grouping | Each message is separate document |
| gdrive token for gmail | Confusing provider key in token store |
| Attachments ignored | Only body text/snippet indexed |

### Alternatives

| Alternative | When |
|-------------|------|
| Batch messages.get | Gmail batch API for throughput |
| Thread-as-document | Conversation-level search |
| Dedicated Gmail OAuth scope UI | Clearer auth separation |
| History API incremental sync | Production-scale mailboxes |

## Security and Resource Notes

| Topic | Detail |
|-------|--------|
| OAuth scope | Requires Gmail read scope on gdrive auth flow |
| Service account | Domain-wide delegation may be required |
| PII | Full email content stored in Supermemory |
| Timeout | 120s per request (large messages) |
| 403/404 on get | Raised as HTTPStatusError, logged per message |
| Env | Uses `SPOON_SYNC_SINCE_DAYS`, `SPOON_MAX_DOCUMENTS_PER_SYNC` |

## Extension Guide

### Include attachments

After `_extract_body`, walk parts for `filename` and `attachmentId`, fetch via `users.messages.attachments.get`, and append extracted text or upload as file documents.

### Filter labels

Extend `_list_query()`:

```python
query = f"{LIST_QUERY} label:important"
```

### Use batch upload

Collect documents in a list and call `upload_document_batch` with multiple docs per call (batch size 20 in ingest) — still respect `can_add_documents()`.

Tests: `tests/test_gmail_normalize.py`
