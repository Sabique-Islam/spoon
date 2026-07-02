# `outlook.py` — Microsoft Outlook Email Sync

## Purpose

`outlook.py` syncs **Outlook / Microsoft 365 mailbox messages** via the Microsoft Graph API. It fetches non-draft messages (optionally filtered by date), converts each to a `Document`, and uploads incrementally with sync quota enforcement.

Authentication uses **Outlook OAuth** (`/api/v1/auth/outlook`).

## Architecture Role

```
Outlook OAuth token (auth store)
        │
        ▼
OutlookConnector.sync()
        │
        ├── _fetch_messages()  — Graph pagination with OData
        └── message_to_document() per message
        │
        ▼
upload_document_batch([doc], result)
        │
        ▼
Supermemory
```

| Component | Role |
|-----------|------|
| Microsoft Graph | `GET /me/messages` with `$filter`, `$select` |
| `_validate_graph_url` | SSRF guard on `@odata.nextLink` |
| `message_to_document` | Graph message → email Document |

## Dependencies

| Import | Module | Usage |
|--------|--------|-------|
| `asyncio`, `logging` | stdlib | Retries, errors |
| `datetime`, `timedelta`, `timezone` | stdlib | Date filter |
| `urlparse` | `urllib.parse` | Host validation for pagination URLs |
| `httpx` | third-party | Graph API HTTP |
| `refresh_outlook_token_if_needed` | `app.auth.outlook_oauth` | Token refresh |
| `get_provider_token` | `app.auth.store` | Auth check |
| `get_settings` | `app.config` | `sync_since_days`, limits |
| `SyncResult`, `upload_document_batch` | `app.connectors.base` | Sync utilities |
| `html_to_text`, `truncate` | `app.connectors.text` | Body processing |
| `Document` | `app.models` | Output model |

## Line-Range Reference

| Lines | Section | Description |
|-------|---------|-------------|
| 1–5 | Imports | stdlib |
| 7 | httpx | HTTP client |
| 9–14 | App imports | auth, config, base, text, models |
| 16 | Logger | `"spoon"` |
| 18 | `GRAPH_API_BASE` | `https://graph.microsoft.com/v1.0` |
| 19–21 | Retry constants | Status codes, retries, page size |
| 22–25 | `MESSAGE_SELECT` | OData fields to retrieve |
| 26 | `MESSAGE_FILTER` | `isDraft eq false` |
| 29–35 | `_message_filter` | Combine draft filter + date filter |
| 38 | `ALLOWED_GRAPH_HOSTS` | `frozenset({"graph.microsoft.com"})` |
| 41–42 | `_truncate` | Delegates to `text.truncate` |
| 45–46 | `_html_to_text` | Wrapper |
| 49–52 | `_validate_graph_url` | Reject untrusted pagination hosts |
| 55–62 | `_format_address` | Graph emailAddress → display string |
| 65–72 | `_format_recipients` | List of recipients → comma-separated |
| 75–83 | `_message_body` | HTML or text body extraction |
| 86–128 | `message_to_document` | Message → Document |
| 131–254 | `OutlookConnector` | Connector class |

### `_fetch_messages` (172–204)

| Lines | Logic |
|-------|-------|
| 175–182 | Initial URL, params with filter/order |
| 184–202 | Pagination loop via `@odata.nextLink` |
| 185–186 | Validate host on subsequent pages |
| 194–197 | 401 → HTTPStatusError |
| 200 | Extend messages from `value` |

### `OutlookConnector.sync` (206–254)

| Lines | Step |
|-------|------|
| 207–213 | Resolve token |
| 216–240 | Fetch messages; 401 refresh retry |
| 242–252 | Process each message with quota check |
| 254 | Return result |

## Functions and Classes

### Constants

| Name | Purpose |
|------|---------|
| `GRAPH_API_BASE` | Graph v1 root |
| `MESSAGE_SELECT` | Fields: id, subject, from, body, dates, etc. |
| `MESSAGE_FILTER` | Exclude drafts |
| `ALLOWED_GRAPH_HOSTS` | Allowed pagination URL hostnames |
| `PAGE_SIZE` | 100 (`$top`) |

### Module functions

| Function | Purpose |
|----------|---------|
| `_message_filter()` | OData filter with optional date |
| `_validate_graph_url(url)` | SSRF protection |
| `_format_address(address)` | Single recipient formatting |
| `_format_recipients(recipients)` | Multiple recipients |
| `_message_body(message)` | Plain or HTML → text |
| `message_to_document(message)` | Graph message → Document |

### `OutlookConnector`

| Method | Description |
|--------|-------------|
| `is_authenticated()` | outlook token in store |
| `_resolve_token()` | Refresh or error |
| `_request(...)` | Bearer + Retry-After aware retries |
| `_fetch_messages(...)` | Full mailbox page set |
| `sync()` | End-to-end sync |

## Tradeoffs

### Pros

| Benefit | Detail |
|---------|--------|
| Pagination URL validation | Mitigates SSRF via malicious `nextLink` |
| Retry-After header | Respects Graph rate limit hints |
| Single list call per page | More efficient than Gmail's per-message list+get |
| Draft exclusion | Filter at API level |
| HTML body support | Converts to plain text |

### Cons

| Limitation | Detail |
|------------|--------|
| No attachment indexing | Body/preview only |
| Full fetch before upload | All messages in memory |
| No per-sync ID cap pre-slice | Unlike Gmail, doesn't truncate ID list early |
| Shared mailbox / folders | Only `/me/messages` default folder behavior |

### Alternatives

| Alternative | When |
|-------------|------|
| `/me/mailFolders/{id}/messages` | Specific folders |
| Delta query | Incremental sync |
| Batch requests | Higher throughput |
| Shared mailbox endpoint | `/users/{id}/messages` |

## Security and Resource Notes

| Topic | Detail |
|-------|--------|
| SSRF guard | `_validate_graph_url` on OData next links |
| Token storage | Outlook tokens in auth store |
| PII | Email content in Supermemory |
| Timeout | 120s per Graph request |
| 401 handling | Prompts re-auth at `/api/v1/auth/outlook` |
| Host allowlist | Only `graph.microsoft.com` for pagination |

## Extension Guide

### Sync specific folder

Change initial URL:

```python
url = f"{GRAPH_API_BASE}/me/mailFolders/inbox/messages"
```

### Add shared mailbox

Use application permissions and `/users/{upn}/messages` with appropriate auth.

### Truncate before processing

After `_fetch_messages`, slice to `settings.max_documents_per_sync` like Gmail does for IDs.

### Test normalizers

`message_to_document` is pure — test with Graph JSON fixtures without HTTP.
