# `app/core/errors.py`

**Source:** [`app/core/errors.py`](../../app/core/errors.py)  
**Lines:** 42

## Purpose

Sanitizes error messages before they are returned to API clients, especially sync error lists that may contain upstream provider responses with URLs, tokens, or secrets.

## Role in the stack

| Function | Caller | Output |
| --- | --- | --- |
| `sanitize_client_error` | `sanitize_sync_errors` | Single safe string |
| `sanitize_sync_errors` | `routes._run_sync` | Truncated, redacted error list |

Original messages are always logged server-side when `context` is provided.

## Dependencies

| Import | Purpose |
| --- | --- |
| `logging` | Log full errors before redaction |
| `re` | Pattern matching for sensitive substrings |

## Constants

| Name | Value | Meaning |
| --- | --- | --- |
| `_MAX_SYNC_ERRORS` | `50` | Max errors returned to client |
| `_SENSITIVE_PATTERNS` | 6 regexes | Substrings that trigger full redaction |

### Sensitive patterns

| Pattern | Matches |
| --- | --- |
| `https?://[^\s]+` | URLs |
| `Bearer\s+\S+` | Bearer tokens |
| `xox[baprs]-\S+` | Slack tokens |
| `ya29\.\S+` | Google OAuth access tokens |
| `token[^\s]*` | Lines mentioning "token" |
| `secret[^\s]*` | Lines mentioning "secret" |

## Line-by-line reference

| Lines | Code | Behavior |
| --- | --- | --- |
| 1–2 | Imports | Logging and regex |
| 4 | `logger` | `"spoon"` logger |
| 6 | `_MAX_SYNC_ERRORS = 50` | Cap client-facing error count |
| 8–15 | `_SENSITIVE_PATTERNS` | Tuple of regex strings |
| 19–28 | `sanitize_client_error()` | Public sanitizer for one message |
| 21–22 | Context logging | If `context` set, log original at ERROR |
| 23–25 | Pattern scan | Any match → generic internal error message |
| 26–27 | Length cap | Messages over 200 chars truncated with `...` |
| 28 | Return | Original message if safe and short |
| 31–41 | `sanitize_sync_errors()` | Batch sanitizer for sync |
| 32 | `sanitized` list | Accumulator |
| 33–36 | Loop first 50 | Each error through `sanitize_client_error` with provider context |
| 37–40 | Truncation notice | If more than 50 errors, append count message |
| 41 | Return | Sanitized list |

## Tradeoffs

| Choice | Benefit | Cost |
| --- | --- | --- |
| Regex redaction | Fast, no provider-specific parsers | False positives (`token` in innocent text) |
| Generic message on match | Strong leak prevention | Operators must read server logs |
| 200-char cap | Limits response size | Long but safe messages truncated |
| 50-error cap | Prevents huge JSON bodies | Remaining errors invisible to client |
| Log on every sanitized error | Full detail in logs | Duplicate logs if many similar errors |

## Security notes

- Always assume connector errors may contain OAuth tokens or internal URLs.
- The `token[^\s]*` and `secret[^\s]*` patterns are broad — prefer logging for forensics.
- Sanitization is not encryption; do not rely on it for logs (see `log_sync` in logging.py).
- Extend patterns when new providers expose distinct secret formats.

## Extension guide

1. **New secret format:** Add regex to `_SENSITIVE_PATTERNS` (e.g. Notion integration tokens).
2. **Structured errors:** Return `{ "code": "...", "message": "..." }` models instead of raw strings.
3. **Error codes:** Map known connector exceptions to stable codes before sanitization.
4. **Testing:** Unit test messages with embedded `ya29.` and Slack tokens assert generic response.
5. **Reuse elsewhere:** Call `sanitize_client_error` from other routes before returning 4xx/5xx details.

## Related documentation

- [routes.md](../routes.md) — applies `sanitize_sync_errors` on sync responses
- [logging.md](../logging.md) — logs unsanitized sync errors at ERROR level
