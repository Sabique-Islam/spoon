# `gdrive.py` — Google Drive File Sync

## Purpose

`gdrive.py` syncs **Google Drive files** into Spoon. It lists non-trashed files (excluding folders and shortcuts), downloads or exports file content, extracts text where possible, and uploads either text documents or raw file blobs to Supermemory.

Authentication uses **Google Drive OAuth** or a **service account**, shared with Gmail.

## Architecture Role

```
Google OAuth / Service Account
        │
        ▼
GDriveConnector.sync()
        │
        ├── _fetch_files()           — Drive files.list
        └── for each file: _process_file()
                │
                ├── _fetch_file_bytes()  — export or media download
                ├── extract_text()       — gdrive_content
                └── upload_document() OR upload_file_document()
        │
        ▼
Supermemory
```

| Path | When used |
|------|-----------|
| Text extraction success | `upload_document(doc)` with extracted text |
| No extractable text | `upload_file_document` with raw bytes + `file_type` |
| Skip | Folders, shortcuts, oversize files, failed exports |

## Dependencies

| Import | Module | Usage |
|--------|--------|-------|
| `asyncio`, `logging` | stdlib | Retries, error logging |
| `httpx` | third-party | Drive API v3 |
| `has_service_account_fallback` | `app.auth.gdrive_oauth` | SA availability check |
| `service_account_token` | `app.auth.google_service_account` | SA token |
| `get_provider_token` | `app.auth.store` | OAuth token check |
| `get_settings` | `app.config` | Limits, max file bytes |
| `SyncResult` | `app.connectors.base` | Sync outcome (no batch helper) |
| `gdrive_content.*` | `app.connectors.gdrive_content` | MIME, extract, file type |
| `Document` | `app.models` | Output model |
| `upload_document`, `upload_documents`, `upload_file_document` | `app.supermemory.ingest` | Ingest paths |

Note: `upload_documents` is imported but unused in current code.

## Line-Range Reference

| Lines | Section | Description |
|-------|---------|-------------|
| 1–3 | Imports | asyncio, logging, typing |
| 5 | httpx | Async HTTP |
| 7–20 | App imports | auth, config, base, gdrive_content, models, ingest |
| 22 | Logger | `"spoon"` |
| 24 | `DRIVE_API_BASE` | `https://www.googleapis.com/drive/v3` |
| 25–27 | Retry constants | Status codes, retries, page size |
| 29–33 | `LIST_QUERY` | Exclude trashed, folders, shortcuts |
| 34–36 | `LIST_FIELDS` | Partial response fields for list |
| 39–76 | `file_to_document` | File metadata + content → Document |
| 79–82 | `_truncate` | Lazy import of `text.truncate` |
| 85–323 | `GDriveConnector` | Main connector class |

### `file_to_document` (39–76)

| Lines | Logic |
|-------|-------|
| 40–42 | file_id, name, mime_type |
| 44–48 | Optional description + content body |
| 50–57 | Detail lines: type, mime, timestamps |
| 59 | Join body + details, truncate |
| 61–76 | Build Document with metadata |

### `GDriveConnector` class (85–323)

| Lines | Member | Description |
|-------|--------|-------------|
| 86 | `provider` | `"gdrive"` |
| 88–92 | `is_authenticated` | OAuth token or SA fallback |
| 94–107 | `_resolve_token` | OAuth refresh, then SA |
| 109–131 | `_request` | Bearer HTTP with exponential backoff |
| 133–167 | `_fetch_files` | Paginated files.list |
| 169–182 | `_download_export` | Google Apps export endpoint |
| 184–196 | `_download_media` | Binary download `alt=media` |
| 198–233 | `_fetch_file_bytes` | Export chain or media download |
| 235–264 | `_process_file` | Extract, upload text or file |
| 266–323 | `sync` | List files, process with limit |

### `_fetch_file_bytes` (198–233)

| Lines | Logic |
|-------|-------|
| 204–205 | file_id, mime_type |
| 207–208 | Skip folders/shortcuts/etc. |
| 210–223 | Google Apps: try each export MIME, size check |
| 225–233 | Regular files: media download, size check |

### `_process_file` (235–264)

| Lines | Logic |
|-------|-------|
| 241–242 | name, mime_type |
| 244–246 | Fetch bytes or return False |
| 248–250 | extract_text; file_to_document with text or filename |
| 252–254 | If text: upload_document |
| 256–263 | Else: upload_file_document with supermemory_file_type |

### `sync` (266–323)

| Lines | Logic |
|-------|-------|
| 269–273 | Token resolution |
| 275 | processed counter |
| 278–304 | Fetch file list; 401 refresh path |
| 306–319 | Loop files until max_documents_per_sync |
| 321 | Set documents_processed |
| 323 | Return result |

## Functions and Classes

### Constants

| Name | Value / Purpose |
|------|-----------------|
| `DRIVE_API_BASE` | Drive API v3 root |
| `LIST_QUERY` | Query string excluding trash/folders/shortcuts |
| `LIST_FIELDS` | Partial resource fields for efficiency |
| `PAGE_SIZE` | 100 |
| `MAX_RETRIES` | 3 |

### Module functions

| Function | Purpose |
|----------|---------|
| `file_to_document(file_meta, content)` | Merge metadata and text into Document |
| `_truncate(content)` | Content length limit |

### `GDriveConnector`

| Method | Description |
|--------|-------------|
| `is_authenticated()` | Token or SA available |
| `_resolve_token()` | Get bearer token |
| `_request(...)` | HTTP with retries (120s timeout) |
| `_fetch_files(...)` | All matching file metadata |
| `_download_export(...)` | Export Google Workspace file |
| `_download_media(...)` | Download binary content |
| `_fetch_file_bytes(...)` | Bytes + effective MIME or None |
| `_process_file(...)` | Full per-file pipeline |
| `sync()` | Orchestrate sync |

## Tradeoffs

### Pros

| Benefit | Detail |
|---------|--------|
| Dual upload strategy | Text search + binary file ingest |
| Export format fallback | Tries multiple exports per Google type |
| Size limits | Skips files over `max_file_bytes` |
| Per-file error isolation | One failure doesn't stop sync |
| Shared Google auth | Same as Gmail |

### Cons

| Limitation | Detail |
|------------|--------|
| No incremental sync | Full file list every run |
| Sequential processing | One file at a time |
| Manual processed count | Doesn't use `upload_document_batch` |
| Unused import | `upload_documents` imported unused |
| Empty text uses filename | Document content may be just filename |

### Alternatives

| Alternative | When |
|-------------|------|
| Changes API / sync tokens | Incremental updates |
| Parallel downloads | Large drives |
| Shared Drive support | Team drives query |
| Always text or always binary | Simpler ingest policy |

## Security and Resource Notes

| Topic | Detail |
|-------|--------|
| Token | OAuth or service account JSON path |
| File size cap | `max_file_bytes` (default 25 MB) |
| Download timeout | 120 seconds per request |
| Untrusted content | Office/PDF parsing in gdrive_content |
| Quota | `max_documents_per_sync` stops processing loop |
| 403/404 | Skipped silently for export/media |

## Extension Guide

### Include Shared Drives

Add `supportsAllDrives=true` and `includeItemsFromAllDrives=true` to list/download params; extend `LIST_QUERY` if needed.

### Use upload_document_batch

Replace direct `upload_document` calls with batch helper for consistent error/limit handling.

### Filter by modified time

Extend `LIST_QUERY`:

```python
LIST_QUERY = "trashed=false and modifiedTime > '2024-01-01T00:00:00'"
```

### Test file normalization

See `tests/test_gdrive_normalize.py` for `file_to_document` patterns.

Tests: `tests/test_sync_gdrive.py`
