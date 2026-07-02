# `app/core/errors.py`

**Source:** [`app/core/errors.py`](../../app/core/errors.py)  
**Lines:** ~30

## Purpose

Sanitizes error messages before they are returned to API clients, especially sync error lists that may contain upstream provider responses with URLs, tokens, or secrets — while still preserving genuinely helpful, non-sensitive guidance (e.g. "re-authenticate at ...").

> **Fixed during the July 2026 security audit follow-up:** the previous patterns matched the bare words `token` and `secret` anywhere in a message, which silently destroyed useful errors like *"Notion token expired. Re-authenticate at /api/v1/auth/notion."* — turning them into a generic, unhelpful "internal error occurred" message. The patterns now only fire on messages that contain an actual secret-shaped value.

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
| `_SENSITIVE_PATTERNS` | 8 regexes | Substrings that trigger full redaction |

### Sensitive patterns

| Pattern | Matches | Notes |
| --- | --- | --- |
| `https?://[^\s]+` | Absolute URLs | Query strings can embed tokens/keys |
| `Bearer\s+\S+` | `Authorization: Bearer <value>` headers | Actual header value, not the word "Bearer" alone |
| `xox[baprs]-\S+` | Slack tokens (bot/user/app/refresh/legacy) | Specific Slack token prefix |
| `ya29\.\S+` | Google OAuth access tokens | Specific Google prefix |
| `AKIA[0-9A-Z]{16}` | AWS access key IDs | **New** — defense in depth, not currently emitted by any connector |
| `-----BEGIN [A-Z ]*PRIVATE KEY-----` | PEM private key material | **New** — defense in depth |
| `\b(?:token\|secret\|password\|api[_-]?key\|client[_-]?secret)\s*[:=]\s*\S+` | A **labeled assignment**, e.g. `token=abc123`, `secret: xyz` | **Rewritten.** Requires `=`/`:` followed by a value — the bare word alone (e.g. "token expired") no longer matches. |
| `\b[A-Za-z0-9_-]{40,}\b` | Long opaque strings (hashes, JWTs, random keys) | **New** — catches secret-shaped values even without a "token=" label |

## Line-by-line reference

| Section | Code | Behavior |
| --- | --- | --- |
| Imports | Logging and regex | Unchanged |
| `logger` | `"spoon"` logger | Unchanged |
| `_MAX_SYNC_ERRORS = 50` | Cap client-facing error count | Unchanged |
| `_SENSITIVE_PATTERNS` | Tuple of 8 regex strings | See table above; two patterns rewritten, three patterns added |
| `sanitize_client_error()` | Context logging → pattern scan → length cap → return | Logic unchanged; only the pattern list changed |
| `sanitize_sync_errors()` | Loop first 50 through `sanitize_client_error`, append truncation notice if needed | Unchanged |

## Verifying the fix

```python
from app.core.errors import sanitize_client_error

# Helpful messages now pass through untouched:
sanitize_client_error("Notion token expired. Re-authenticate at /api/v1/auth/notion.")
# -> "Notion token expired. Re-authenticate at /api/v1/auth/notion."

# Actual secrets are still redacted:
sanitize_client_error("access_token=ya29.a0AfH6SMC1234567890")
# -> "An internal error occurred. Check server logs for details."
```

See `tests/test_security.py::test_error_sanitizer_preserves_helpful_reauth_messages` and `::test_error_sanitizer_redacts_actual_secrets` for the full regression-test matrix (Notion/Google/Outlook/Slack/Linear re-auth strings, plus Bearer/`ya29.`/`client_secret=`/URL/Slack-token leak cases).

## Tradeoffs

| Choice | Benefit | Cost |
| --- | --- | --- |
| Regex redaction | Fast, no provider-specific parsers | Still a blocklist — can miss novel secret formats |
| Labeled-assignment pattern (`token=...`) instead of bare word | Keeps helpful "re-authenticate" messages readable | Slightly more complex regex to maintain |
| 40+ char opaque-string heuristic | Catches unlabeled secrets (raw JWTs, hashes) | Small false-positive risk on long non-secret identifiers (e.g. very long concatenated IDs) — acceptable given the safety-over-verbosity tradeoff |
| Generic message on match | Strong leak prevention | Operators must read server logs |
| 200-char cap | Limits response size | Long but safe messages truncated |
| 50-error cap | Prevents huge JSON bodies | Remaining errors invisible to client |

## Security notes

- Always assume connector errors may contain OAuth tokens or internal URLs — the pattern list is defense in depth, not a substitute for connectors avoiding secret interpolation into error strings in the first place.
- Sanitization is not encryption; do not rely on it for logs (see `log_sync` in `logging.py`, which logs the *unsanitized* error for operators).
- Extend patterns when new providers expose distinct secret formats (e.g. a new provider's token prefix).
- This module fixes a real regression that existed before this pass: broad blocklists can accidentally redact non-sensitive, user-helpful text. When adding new patterns, always add a matching "should NOT be redacted" test case alongside a "should be redacted" one.

## Extension guide

1. **New secret format:** Add a regex to `_SENSITIVE_PATTERNS` (e.g. a new provider's token prefix), and add both a positive (redacted) and negative (preserved) test.
2. **Structured errors:** Return `{ "code": "...", "message": "..." }` models instead of raw strings.
3. **Error codes:** Map known connector exceptions to stable codes before sanitization.
4. **Reuse elsewhere:** Call `sanitize_client_error` from other routes before returning 4xx/5xx details.

## Related documentation

- [routes.md](../routes.md) — applies `sanitize_sync_errors` on sync responses
- [logging.md](../logging.md) — logs unsanitized sync errors at ERROR level
- `tests/test_security.py` — regression tests for both redaction and preservation behavior
