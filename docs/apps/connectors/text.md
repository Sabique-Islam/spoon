# `text.py` — Text Normalization Utilities

## Purpose

`text.py` provides two small, shared text-processing functions used across email and document connectors:

- **`truncate`** — Enforces maximum content length from application settings.
- **`html_to_text`** — Strips HTML tags and decodes entities into plain text.

These utilities keep content normalization consistent and avoid duplicating regex logic in Gmail, Outlook, and `base.py`.

## Architecture Role

```
Gmail / Outlook connectors          base.py (SyncResult.truncate)
        │                                    │
        └──────────► text.py ◄───────────────┘
                         │
              truncate() / html_to_text()
                         │
              Plain, length-bounded strings
                         │
              Document.content field
```

| Function | Primary consumers |
|----------|-------------------|
| `truncate` | `base.SyncResult`, Gmail, Outlook (via wrappers) |
| `html_to_text` | Gmail, Outlook (HTML email bodies) |

Note: Linear, Slack, Notion, and GDrive use local truncate implementations or inline slicing rather than importing `text.truncate` directly (except GDrive which imports it lazily inside `_truncate`).

## Dependencies

| Import | Module | Usage |
|--------|--------|-------|
| `re` | stdlib | Tag stripping, whitespace collapse |
| `unescape` | `html` | Decode HTML entities (`&amp;`, etc.) |
| `get_settings` | `app.config` | Read `max_content_length` |

## Line-Range Reference

| Lines | Section | Description |
|-------|---------|-------------|
| 1–4 | Imports | `re`, `html.unescape`, settings |
| 7–8 | `truncate` | Slice content to `max_content_length` |
| 11–19 | `html_to_text` | Remove script/style, strip tags, normalize whitespace |

## Functions

### `truncate(content: str) -> str`

| Aspect | Detail |
|--------|--------|
| Input | Any string |
| Output | First `max_content_length` characters (default 100,000) |
| Config | `SPOON_MAX_CONTENT_LENGTH` / `settings.max_content_length` |
| Side effects | None |

Simple prefix truncation — no word boundary awareness.

### `html_to_text(html: str) -> str`

| Step | Lines | Action |
|------|-------|--------|
| 1 | 12–17 | Remove `<script>` and `<style>` blocks (case-insensitive, DOTALL) |
| 2 | 18 | Replace remaining tags with space |
| 3 | 19 | `unescape` entities, collapse whitespace, strip ends |

| Aspect | Detail |
|--------|--------|
| Input | HTML string |
| Output | Plain text, single-space separated |
| Not handled | Tables, lists structure, inline CSS, complex layout |

## Tradeoffs

### Pros

| Benefit | Detail |
|---------|--------|
| Minimal and fast | No external HTML parser dependency |
| Shared config | One setting controls all truncation |
| Safe script removal | Strips script/style before tag removal |
| Entity decoding | Handles common HTML entities |

### Cons

| Limitation | Detail |
|------------|--------|
| Naive HTML parsing | Regex tag removal can mishandle malformed HTML |
| No structure preservation | Headings, lists become flat text |
| Hard truncate | May cut mid-word or mid-sentence |
| Duplicate truncate paths | Some connectors reimplement truncate locally |

### Alternatives

| Alternative | Use when |
|-------------|----------|
| `html2text` / `beautifulsoup4` | Richer HTML → markdown/text needed |
| `lxml` / `html.parser` | Same approach as `gdrive_content._extract_html` |
| Token-aware truncation | LLM context limits require semantic cuts |
| Central truncate only | Remove duplicate `_truncate` in linear/slack/gmail |

## Security and Resource Notes

| Topic | Detail |
|-------|--------|
| HTML injection | Output is plain text for storage/search, not re-rendered as HTML |
| ReDoS risk | Low for typical email sizes; script/style regex uses non-greedy match |
| Memory | Full string held in memory; bounded by upstream content + truncate |
| No external fetch | Operates only on provided strings |

## Extension Guide

### Using in a new connector

```python
from app.connectors.text import truncate, html_to_text

body = html_to_text(raw_html) if is_html else raw_plain
content = truncate(body)
```

### Improving HTML conversion

If email fidelity matters, replace `html_to_text` internals with an HTML parser while keeping the same function signature so Gmail/Outlook need no changes.

### Adding markdown or strip helpers

Add new functions to this module rather than connector-local copies. Export through `SyncResult.truncate` only if all connectors should use the new behavior.

Example:

```python
def strip_null_bytes(content: str) -> str:
    return content.replace("\x00", "")
```

Call before `truncate` in connectors that ingest binary-decoded text.
