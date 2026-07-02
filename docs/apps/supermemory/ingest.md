# `app/supermemory/ingest.py`

**Source:** [`app/supermemory/ingest.py`](../../app/supermemory/ingest.py)  
**Lines:** 91

## Purpose

Uploads connector-produced `Document` objects to Supermemory as text documents, batched text adds, or binary file uploads with sanitized IDs and normalized metadata.

## Role in the stack

| Function | When used |
| --- | --- |
| `upload_document` | Single text document |
| `upload_documents` | Batch text sync (primary connector path) |
| `upload_file_document` | PDFs, images, and other binary exports |

Called from connector implementations after normalization to [models.md](../models.md) `Document`.

## Dependencies

| Import | Purpose |
| --- | --- |
| `hashlib` | SHA-256 for `custom_id` suffix |
| `get_settings` | `container_tag`, `max_file_bytes` |
| `Document` | Source model |
| `get_supermemory_client` | SDK client |
| `json` (inline in `upload_file_document`) | Metadata serialization for file API |

## Constants

| Name | Value | Purpose |
| --- | --- | --- |
| `BATCH_SIZE` | `20` | Documents per `batch_add` call |

## Line-by-line reference

| Lines | Code | Behavior |
| --- | --- | --- |
| 1 | `import hashlib` | Document ID hashing |
| 3–5 | Imports | Config, Document, client |
| 7 | `BATCH_SIZE = 20` | Batch upload chunk size |
| 10–14 | `_sanitize_custom_id()` | Supermemory-safe custom ID |
| 11 | SHA-256 digest | First 32 hex chars of `doc_id` |
| 12 | Prefix | First 20 chars of `doc_id`, alnum `-_.` only else `-` |
| 13 | Fallback prefix | `"doc"` if prefix empty after strip |
| 14 | Return | `{prefix}-{digest}` max 100 chars |
| 17–29 | `_build_metadata()` | Flat metadata dict for Supermemory |
| 18–23 | Core fields | `source`, `title`, `url`, `document_id` |
| 24–28 | Extra from doc | Scalar types as-is; other non-None → `str()` |
| 29 | Return metadata | Merged dict |
| 32–39 | `_doc_to_payload()` | Text upload shape |
| 33 | settings | For container tag |
| 34–38 | Payload keys | `content`, `custom_id`, `metadata`, `container_tag` |
| 42–45 | `upload_document()` | Single add via SDK |
| 43–45 | client.documents.add | Unpacks payload kwargs |
| 47–74 | `upload_file_document()` | Binary upload path |
| 56–58 | Size check | Raises `ValueError` if over `max_file_bytes` |
| 60 | import json | Local import for metadata JSON string |
| 62–69 | kwargs | file tuple, container_tag, custom_id, metadata JSON |
| 70–71 | Optional file_type | Passed if provided |
| 72–73 | mime_type | Set for image/* and video/* |
| 74 | upload_file | SDK binary upload |
| 77–90 | `upload_documents()` | Batched text upload |
| 78–79 | Empty guard | No-op if list empty |
| 81–82 | Client + settings | SDK and tag |
| 84–85 | Batch loop | Steps of `BATCH_SIZE` |
| 86 | Build payloads | List comp `_doc_to_payload` |
| 87–90 | batch_add | SDK batch with shared `container_tag` |

## Data flow

```
Document (connector)
  → _sanitize_custom_id(doc.id)
  → _build_metadata(doc)
  → _doc_to_payload(doc)  OR  file bytes path
  → Supermemory API (add / batch_add / upload_file)
```

## Metadata typing rules

| `doc.metadata` value type | Stored as |
| --- | --- |
| `str`, `int`, `float`, `bool` | Original value |
| Other non-None | `str(value)` |
| None | Omitted |

## Tradeoffs

| Choice | Benefit | Cost |
| --- | --- | --- |
| Hashed `custom_id` | Stable dedup despite special chars in source IDs | Original ID only in metadata |
| Batch size 20 | Fewer API round trips | Partial batch failure handling delegated to SDK |
| Scalar metadata filter | Supermemory-compatible values | Nested objects stringified |
| Local `json` import | Avoid top-level dep in text-only paths | Inconsistent import style |
| Separate file upload API | Supports binary MIME types | Metadata passed as JSON string not dict |

## Security notes

- Enforce `max_file_bytes` before upload to avoid memory exhaustion (default 25 MB).
- `doc.content` may contain PII from mail/docs — Supermemory stores content per their policy.
- `custom_id` derivation is one-way truncated hash — not for security, only ID format.
- Filenames in `upload_file_document` come from connectors — sanitize path traversal in callers.

## Extension guide

1. **Upsert semantics:** Rely on stable `custom_id` — re-upload same ID updates if SDK supports it.
2. **Larger batches:** Tune `BATCH_SIZE` vs Supermemory API limits.
3. **Delete stale docs:** Add `delete_document(custom_id)` wrapper when sources remove content.
4. **Content truncation:** Truncate `doc.content` to `max_content_length` from config before payload build.
5. **Async batching:** Parallelize batches with semaphore if rate limits allow.
6. **Structured metadata:** Whitelist keys per `doc.source` in `_build_metadata`.

## Related documentation

- [client.md](./client.md) — SDK entry
- [models.md](../models.md) — `Document` schema
- [config.md](../config.md) — `container_tag`, `max_file_bytes`, `max_content_length`
- [search.md](./search.md) — queries same container tag
