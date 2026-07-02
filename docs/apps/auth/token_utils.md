# `token_utils.py` — OAuth Token Merge and Refresh Timing

`token_utils.py` contains two small utilities used by OAuth providers that support refresh tokens: merging new token responses with existing stored data, and deciding when an access token should be refreshed before it expires.

---

## Role in Spoon Architecture

After OAuth token exchange or refresh, providers must persist a consistent token dict (access token, refresh token, expiry). Before API calls, providers check whether the access token is still valid. This module centralizes that logic so Google, Notion, and Outlook modules stay consistent.

```
Token exchange/refresh response
        │
        ▼
merge_oauth_token(provider, response, extra={...})
        │
        ▼
set_provider_token()  [in provider module]

Before API call
        │
        ▼
token_needs_refresh(stored) ──▶ refresh_access_token() if True
```

Used by: `gdrive_oauth.py`, `notion_oauth.py`, `outlook_oauth.py`. **Not** used by `slack_oauth.py` (Slack bot tokens don't use this refresh pattern in Spoon).

---

## Dependencies

### What this module imports

| Import | Source | Purpose |
|--------|--------|---------|
| `time` | stdlib | Current time for expiry calculation |
| `Any` | `typing` | Dict typing |
| `get_provider_token` | `app.auth.store` | Load existing tokens when merging |

### What imports this module

| Consumer | Symbols used |
|----------|----------------|
| `app/auth/gdrive_oauth.py` | `merge_oauth_token`, `token_needs_refresh` |
| `app/auth/notion_oauth.py` | `merge_oauth_token`, `token_needs_refresh` |
| `app/auth/outlook_oauth.py` | `merge_oauth_token`, `token_needs_refresh` |

---

## Line-by-Line Reference

| Lines | Code / Section | Explanation |
|-------|----------------|-------------|
| 1 | `import time` | Used for `expires_at` computation and refresh checks. |
| 2 | `from typing import Any` | Type hints for token dicts. |
| 3 | *(blank)* | Separator. |
| 4 | `from app.auth.store import get_provider_token` | Reads existing provider tokens during merge. |
| 5 | *(blank)* | Separator. |
| 7–29 | `merge_oauth_token()` | Builds normalized token dict from OAuth response + existing data. |
| 13 | `existing = get_provider_token(provider) or {}` | Preserves refresh token if new response omits it (common on refresh). |
| 14–19 | Core fields | Always sets `access_token`; merges `refresh_token` and `token_type` from response or existing. |
| 15 | `token_response["access_token"]` | Required field; KeyError if missing (OAuth responses always include it). |
| 16–17 | Refresh token merge | New refresh token wins; else keep existing (Google often omits refresh on refresh). |
| 21–24 | Expiry handling | If `expires_in` present, stores it and computes `expires_at` with 60-second buffer. |
| 24 | `time.time() + int(expires_in) - 60` | Refresh one minute before actual expiry to avoid edge-case 401s. |
| 26–27 | `extra` dict | Provider-specific fields (e.g. Notion `workspace_id`) merged last. |
| 29 | `return data` | Caller passes to `set_provider_token`. |
| 31–40 | `token_needs_refresh()` | Returns whether caller should refresh before using access token. |
| 33–34 | No stored data | Returns `False` (nothing to refresh). |
| 35–36 | No refresh token | Returns `False` (cannot refresh; use static token or re-auth). |
| 37–39 | Missing `expires_at` | Returns `True` (assume stale; attempt refresh). |
| 40 | `time.time() >= float(expires_at)` | True when past buffered expiry time. |

---

## Key Functions

| Function | Parameters | Returns | Purpose |
|----------|------------|---------|---------|
| `merge_oauth_token` | `provider`, `token_response`, `extra=None` | `dict[str, Any]` | Normalize and merge OAuth token fields for persistence. |
| `token_needs_refresh` | `stored` | `bool` | True if stored token should be refreshed before use. |

---

## Stored Token Fields (after merge)

| Field | Source | Notes |
|-------|--------|-------|
| `access_token` | Always from latest response | Required for API calls |
| `refresh_token` | Response or existing | Preserved across refresh responses that omit it |
| `token_type` | Response or existing | Usually `Bearer` |
| `expires_in` | Response (optional) | Seconds until expiry from provider |
| `expires_at` | Computed | Unix timestamp; refresh triggered when `now >= expires_at` |
| *(extra)* | Provider `extra` arg | e.g. `workspace_id`, `workspace_name` |

---

## Design Choices & Tradeoffs

| Choice | Advantage | Drawback | Alternative |
|--------|-----------|----------|-------------|
| 60-second expiry buffer | Avoids using tokens in their last seconds | Refreshes slightly early (extra token requests) | Buffer configurable per provider |
| Preserve refresh token on merge | Matches OAuth provider behavior (no new refresh every time) | Stale refresh token if provider rotates and omits new one | Always overwrite from response only |
| `expires_at` missing → needs refresh | Safe default for unknown expiry | May refresh unnecessarily | Store `None` and skip refresh |
| No refresh token → `False` | Avoids infinite failed refresh loops | Access token may expire with no recovery | Force re-auth flag |
| Loads existing inside merge | Single call site for providers | Extra disk read per merge | Pass existing dict as parameter |

---

## Security Considerations

- **Refresh tokens** persisted via merge are long-lived; protect the token store (see `store.md`).
- **No token logging** in this module — ensure callers don't log merged dicts.
- **Clock skew**: Expiry uses server local time; large skew vs OAuth provider can cause premature or late refresh.
- **`expires_in` trust**: Assumes provider's `expires_in` is accurate; no introspection endpoint validation.

---

## When and How to Extend

### Use in a new OAuth provider with refresh

```python
from app.auth.token_utils import merge_oauth_token, token_needs_refresh

async def store_oauth_token(token_response):
    set_provider_token(
        PROVIDER,
        merge_oauth_token(PROVIDER, token_response, extra={"custom": "fields"}),
    )

async def refresh_*_token_if_needed():
    stored = get_provider_token(PROVIDER)
    if not token_needs_refresh(stored):
        return stored.get("access_token")
    # ... refresh and store ...
```

### Adjust refresh buffer

Change `- 60` in line 24 to a constant (e.g. `REFRESH_BUFFER_SECONDS = 120`).

### Handle providers that return absolute expiry

Some APIs return `expires_at` directly instead of `expires_in`. Extend `merge_oauth_token` to accept either format.

### Slack-style tokens without refresh

Do not use this module; build token dict manually in `store_oauth_token` like `slack_oauth.py`.
