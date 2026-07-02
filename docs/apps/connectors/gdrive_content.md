# `gdrive_content.py` — Google Drive File Text Extraction

## Purpose

`gdrive_content.py` handles **binary and Google Workspace file content extraction** for the Google Drive connector. It:

- Maps Google Apps MIME types to export formats.
- Extracts plain text from PDF, DOCX, XLSX, PPTX, HTML, and plain text files.
- Classifies files for Supermemory's file upload API via `supermemory_file_type`.

This module is used by `gdrive.py` after file bytes are downloaded or exported from Drive.

## Architecture Role

```
GDriveConnector._fetch_file_bytes()
        │
        ▼
extract_text(filename, mime_type, data)
        │
        ├── Text path → upload_document (text content)
        └── Binary/no text → upload_file_document (raw bytes)
                │
                └── supermemory_file_type() for file_type hint
```

| Function category | Role |
|-------------------|------|
| MIME helpers | `is_google_app`, `export_formats_for`, `should_skip_mime_type` |
| Extractors | `_extract_pdf`, `_extract_docx`, etc. |
| Public API | `extract_text`, `supermemory_file_type` |

## Dependencies

| Import | Module | Usage |
|--------|--------|-------|
| `json`, `logging` | stdlib | Logging only (`json` imported but unused in current file) |
| `HTMLParser` | `html.parser` | `_HTMLTextExtractor` |
| `BytesIO` | `io` | In-memory file reads |
| Optional | `pypdf` | PDF text extraction |
| Optional | `docx` (python-docx) | Word documents |
| Optional | `openpyxl` | Excel spreadsheets |
| Optional | `pptx` (python-pptx) | PowerPoint |

Optional libraries are imported inside extractor functions; missing deps log a warning and return `None`.

## Line-Range Reference

| Lines | Section | Description |
|-------|---------|-------------|
| 1–6 | Imports & logger | stdlib imports, `"spoon"` logger |
| 8–16 | MIME constants | `TEXT_MIME_PREFIXES`, `TEXT_MIME_TYPES` |
| 18–42 | `GOOGLE_EXPORT_FORMATS` | Google Apps type → export MIME list |
| 44–49 | `SKIP_GOOGLE_MIME_TYPES` | Folders, shortcuts, forms, maps |
| 52–62 | `_HTMLTextExtractor` | HTMLParser subclass collecting text nodes |
| 65–66 | `is_google_app` | True if MIME starts with `application/vnd.google-apps.` |
| 69–74 | `export_formats_for` | Preferred export formats per Google type |
| 77–78 | `should_skip_mime_type` | Membership in skip set |
| 81–87 | `_decode_text` | Try utf-8, utf-16, latin-1; fallback replace |
| 90–100 | `_extract_pdf` | pypdf page text join |
| 103–112 | `_extract_docx` | Paragraph text from Word |
| 115–129 | `_extract_xlsx` | Row cells joined with ` \| ` |
| 132–148 | `_extract_pptx` | Shape text per slide |
| 151–155 | `_extract_html` | Feed bytes through HTML parser |
| 158–205 | `extract_text` | Main dispatch by MIME/extension |
| 208–229 | `supermemory_file_type` | Map to Supermemory file type string |

### `extract_text` dispatch (158–205)

| Lines | Branch | Behavior |
|-------|--------|----------|
| 159–160 | Empty data | Return `None` |
| 162–163 | Normalize MIME, extension | Lowercase |
| 165–167 | Text MIME types | `_decode_text`, strip |
| 169–170 | HTML MIME | `_extract_html` |
| 172–173 | PDF | `_extract_pdf` |
| 175–180 | DOCX | `_extract_docx` |
| 182–186 | XLSX | `_extract_xlsx` |
| 188–193 | PPTX | `_extract_pptx` |
| 195–196 | Legacy MS Office | Return `None` (no extractor) |
| 198–199 | Image/video/audio | Return `None` |
| 201–205 | Heuristic fallback | Decode if >85% printable chars |

### `GOOGLE_EXPORT_FORMATS` (18–42)

| Google MIME | Export formats tried (in order) |
|-------------|--------------------------------|
| document | text/plain, text/html, application/pdf |
| spreadsheet | text/csv, application/pdf |
| presentation | text/plain, application/pdf |
| drawing | application/pdf, image/png |
| site | text/html |
| script | application/vnd.google-apps.script+json |

## Functions and Classes

### `_HTMLTextExtractor`

| Method | Description |
|--------|-------------|
| `handle_data(data)` | Append non-empty stripped text |
| `text()` | Join parts with newlines |

### Public functions

| Function | Returns | Description |
|----------|---------|-------------|
| `is_google_app(mime_type)` | `bool` | Google Workspace native file |
| `export_formats_for(mime_type)` | `list[str]` | Export MIME candidates |
| `should_skip_mime_type(mime_type)` | `bool` | Non-syncable types |
| `extract_text(filename, mime_type, data)` | `str \| None` | Extracted plain text |
| `supermemory_file_type(mime_type, filename)` | `str \| None` | Supermemory upload hint |

## Tradeoffs

### Pros

| Benefit | Detail |
|---------|--------|
| Graceful optional deps | Missing library → warning, not crash |
| Multi-format Google export | Tries plain text before PDF for Docs |
| Extension + MIME dispatch | Handles mislabeled files |
| Printable heuristic | Salvages unknown text-like binaries |

### Cons

| Limitation | Detail |
|------------|--------|
| PDF/OCR quality | pypdf text extraction is layout-naive |
| No legacy .doc/.xls | Explicitly returns None |
| XLSX loses structure | Flat pipe-separated rows |
| Duplicate HTML parsing | Different from `text.html_to_text` |
| Unused `json` import | Minor cleanup opportunity |

### Alternatives

| Alternative | When |
|-------------|------|
| Unified MIME registry | Many more file types |
| Tesseract OCR for PDF/images | Scanned documents |
| Apache Tika | One dependency for many formats |
| Always upload binary | Skip text extraction entirely |

## Security and Resource Notes

| Topic | Detail |
|-------|--------|
| File size | Enforced in `gdrive.py` via `max_file_bytes` before calling extractors |
| Malicious PDF/Office | Parsing untrusted files — keep optional deps updated |
| Memory | Full file loaded into `BytesIO`; bounded by `max_file_bytes` |
| No network | Operates on bytes already downloaded |
| Logging | Warnings only when optional libs missing |

## Extension Guide

### Add a new format (e.g. RTF)

1. Add optional import extractor:

```python
def _extract_rtf(data: bytes) -> str | None:
    try:
        from striprtf.striprtf import rtf_to_text
    except ImportError:
        logger.warning("striprtf not installed")
        return None
    return rtf_to_text(_decode_text(data)) or None
```

2. Add branch in `extract_text` for MIME `application/rtf` or extension `rtf`.

3. Optionally add to `TEXT_MIME_TYPES` if treating as text.

### Add Google Apps type

Extend `GOOGLE_EXPORT_FORMATS` and verify export works via Drive API in `gdrive._fetch_file_bytes`.

### Supermemory type mapping

Add cases to `supermemory_file_type` for new categories Supermemory supports (see ingest API docs).
