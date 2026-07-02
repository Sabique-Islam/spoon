# `oauth.py` — Shared OAuth HTTP Helpers

`oauth.py` provides small, reusable building blocks for OAuth token exchange and HTTP Basic authentication. It does not implement a full provider flow; instead, provider modules (`gdrive_oauth`, `notion_oauth`, etc.) call these helpers when talking to authorization servers. State generation is re-exported from `state.py` so callers can import everything OAuth-related from one place.

> **Updated during the July 2026 security audit follow-up:** `validate_oauth_state` is no longer re-exported (or defined) — it was dead code that duplicated `pop_oauth_state`'s destructive "consume" behavior and risked a double-pop bug if ever wired up. Only `generate_oauth_state` is re-exported now. See [state.md](./state.md) for details.

---

## Role in Spoon Architecture

Spoon connects to third-party services (Google Drive, Notion, Slack, Outlook) via OAuth 2.0. Each provider module builds authorization URLs and exchanges codes for tokens, but the HTTP mechanics differ slightly (form POST vs JSON POST, Basic auth headers). `oauth.py` sits in the **shared auth layer** between provider-specific modules and external OAuth endpoints.

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────────┐
│ Provider modules│────▶│   oauth.py   │────▶│ External OAuth APIs │
│ (gdrive, notion)│     │ (HTTP helpers)│     │ (Google, Notion, …) │
└─────────────────┘     └──────┬───────┘     └─────────────────────┘
                                 │
                                 ▼
                         ┌──────────────┐
                         │   state.py   │
                         │ (CSRF state) │
                         └──────────────┘
```

The FastAPI routes in `app/routes.py` never import `oauth.py` directly; they go through `providers.py` and provider modules that use these helpers internally.

---

## Dependencies

### What this module imports

| Import | Source | Purpose |
|--------|--------|---------|
| `base64` | stdlib | Encode client credentials for Basic auth |
| `typing.Any` | stdlib | Type hints for JSON payloads |
| `httpx` | third-party | Async HTTP client for token exchange |
| `generate_oauth_state` | `app.auth.state` | CSRF state token creation (re-exported) |

### What imports this module

| Consumer | Symbols used |
|----------|----------------|
| `app/auth/gdrive_oauth.py` | `exchange_token_form`, `generate_oauth_state` |
| `app/auth/notion_oauth.py` | `basic_auth_header`, `exchange_token_json`, `generate_oauth_state` |
| `app/auth/outlook_oauth.py` | `exchange_token_form`, `generate_oauth_state` |
| `app/auth/slack_oauth.py` | `generate_oauth_state` |

---

## Line-by-Line Reference

| Lines | Code / Section | Explanation |
|-------|----------------|-------------|
| 1 | `import base64` | Standard library module for Base64 encoding, used in Basic auth header construction. |
| 2 | `from typing import Any` | Allows flexible dict typing for OAuth request/response payloads. |
| 3 | *(blank)* | Visual separator between stdlib and third-party imports. |
| 4 | `import httpx` | Async HTTP client library; used for POST requests to token endpoints. |
| 5 | *(blank)* | Separator before local imports. |
| 6 | `from app.auth.state import generate_oauth_state` | Imports the single state-creation helper and re-exports it via `__all__` for convenience. |
| 7 | *(blank)* | Separator before public API definition. |
| 8–13 | `__all__ = [...]` | Explicit public API: three functions from this file plus `generate_oauth_state` re-exported from `state.py`. (`validate_oauth_state` removed — see update note above.) |
| 15 | *(blank)* | Separator before function definitions. |
| 17–20 | `basic_auth_header()` | Builds an RFC 7617 Basic auth header: `client_id:client_secret` → Base64 → `"Basic …"`. |
| 18 | `credentials = f"{client_id}:{client_secret}"` | Concatenates ID and secret with a colon, per OAuth spec for client authentication. |
| 19 | `encoded = base64.b64encode(...)` | Encodes credentials as ASCII Base64 bytes, then decodes to str for the header value. |
| 20 | `return f"Basic {encoded}"` | Returns the full `Authorization` header value (without the `Authorization:` prefix). |
| 21 | *(blank)* | Separator. |
| 23–27 | `exchange_token_form()` | POSTs `application/x-www-form-urlencoded` data to a token URL; returns parsed JSON. |
| 24 | `async with httpx.AsyncClient() as client:` | Creates a short-lived async HTTP client (new client per call). |
| 25 | `response = await client.post(url, data=payload, timeout=30.0)` | Sends form-encoded POST; 30-second timeout prevents hung requests. |
| 26 | `response.raise_for_status()` | Raises `httpx.HTTPError` on 4xx/5xx responses. |
| 27 | `return response.json()` | Parses response body as JSON dict (typical OAuth token response). |
| 28 | *(blank)* | Separator. |
| 30–38 | `exchange_token_json()` | POSTs JSON body with custom headers (used by Notion). |
| 31–33 | Parameters | `url`, JSON `payload`, and extra `headers` (e.g. Basic auth + Content-Type). |
| 35–37 | HTTP POST | Same pattern as form exchange, but uses `json=payload` and passes `headers`. |
| 38 | `return response.json()` | Returns parsed token response. |

---

## Key Functions

| Function | Signature | What it does |
|----------|-----------|--------------|
| `basic_auth_header` | `(client_id, client_secret) → str` | Creates `Authorization: Basic …` value for OAuth clients that authenticate with HTTP Basic (Notion). |
| `exchange_token_form` | `(url, payload) → dict` | Exchanges authorization codes or refresh tokens via form POST (Google, Microsoft). |
| `exchange_token_json` | `(url, payload, headers) → dict` | Same as above but sends JSON body with custom headers (Notion). |
| `generate_oauth_state` | `(*, pkce_verifier=None) → str` | **Re-export** from `state.py`. Creates a random CSRF state token, optionally storing a PKCE verifier. |

---

## Design Choices & Tradeoffs

| Choice | Advantage | Drawback | Alternative |
|--------|-----------|----------|-------------|
| Separate form vs JSON exchange functions | Clear API; each provider uses the right content type | Two similar functions instead of one parameterized helper | Single function with `content_type` parameter |
| New `httpx.AsyncClient` per call | Simple, no connection pooling bugs across requests | Slight overhead creating clients repeatedly | Shared module-level client with lifecycle management |
| Re-export state functions in `__all__` | Provider modules can import state + HTTP from one module | Blurs module boundaries; `oauth.py` name is slightly misleading | Import state directly in each provider |
| `raise_for_status()` on errors | Fail fast; callers use try/except on `httpx.HTTPError` | No structured OAuth error parsing (e.g. `invalid_grant`) | Parse OAuth error JSON and raise custom exceptions |
| 30-second timeout | Prevents indefinite hangs | May be too long for interactive flows | Configurable timeout via settings |

---

## Security Considerations

- **`basic_auth_header`** embeds the client secret in a header. Only use over HTTPS. The secret never appears in URLs or logs if callers avoid logging headers.
- **Token exchange responses** contain access tokens and sometimes refresh tokens. Callers must pass responses to `store.py` via provider modules; this module does not persist secrets.
- **No retry logic** — a failed exchange fails immediately, which avoids accidental token leakage through repeated requests but may be brittle on transient network errors.
- **State re-exports** tie CSRF protection to the same import path providers already use, reducing the chance providers skip state generation.

---

## When and How to Extend

### Add a provider that uses form-encoded token exchange

1. Import `exchange_token_form` and `generate_oauth_state` from `app.auth.oauth`.
2. Build your authorization URL with `generate_oauth_state()` in the `state` query parameter.
3. On callback, POST your payload to the provider's token URL via `exchange_token_form`.

### Add a provider that uses JSON + Basic auth

1. Import `basic_auth_header`, `exchange_token_json`, and `generate_oauth_state`.
2. Set headers with `Authorization: basic_auth_header(...)` and `Content-Type: application/json`.
3. Call `exchange_token_json` with your payload.

### Add shared OAuth error handling

If multiple providers need structured error parsing, add a helper here (e.g. `parse_oauth_error(response)`) rather than duplicating logic in each provider module.

### Add to `__all__`

Any new public helper should be listed in `__all__` so the module's API surface stays explicit.
