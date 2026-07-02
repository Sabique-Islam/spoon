# `notion_oauth.py` — Notion OAuth Integration

`notion_oauth.py` implements Notion's OAuth 2.0 flow for connecting user workspaces to Spoon. It uses HTTP Basic authentication for token requests (Notion's requirement), JSON token exchange, and stores workspace metadata alongside tokens. Connectors use `refresh_notion_token_if_needed()` and fall back to a static API key if configured.

---

## Role in Spoon Architecture

Notion sync (`app/connectors/notion.py`) obtains access tokens through this module. The generic OAuth routes expose it as provider name `notion`.

```
GET /auth/notion ──▶ build_authorization_url()
        │
GET /auth/notion/callback ──▶ exchange_code_for_token ──▶ store_oauth_token
        │
Notion sync ──▶ refresh_notion_token_if_needed()
        │
        └── fallback: settings.notion_api_key (integration token)
```

Registered in `OAUTH_PROVIDERS` with success message "Notion connected successfully".

---

## Dependencies

### What this module imports

| Import | Source | Purpose |
|--------|--------|---------|
| `typing.Any` | stdlib | Type hints |
| `urlencode` | `urllib.parse` | Authorization URL query string |
| `httpx` | third-party | HTTP errors on refresh |
| `basic_auth_header`, `exchange_token_json`, `generate_oauth_state` | `app.auth.oauth` | Notion-specific token HTTP |
| `get_provider_token`, `set_provider_token` | `app.auth.store` | Persistence |
| `merge_oauth_token`, `token_needs_refresh` | `app.auth.token_utils` | Token merge and refresh |
| `get_settings` | `app.config` | Notion client ID, secret, redirect, API key fallback |

### What imports this module

| Consumer | Symbols used |
|----------|----------------|
| `app/auth/providers.py` | OAuth registry functions |
| `app/connectors/notion.py` | `get_notion_access_token`, `refresh_notion_token_if_needed` |
| `tests/test_security.py` | Security tests |

---

## Line-by-Line Reference

| Lines | Code / Section | Explanation |
|-------|----------------|-------------|
| 1–13 | Imports | urllib, httpx, auth helpers, config. |
| 15–17 | Constants | Notion OAuth URLs and provider key `"notion"`. |
| 20–32 | `build_authorization_url()` | Builds Notion authorize URL with state (no PKCE). |
| 22–23 | Config guard | Raises if Notion OAuth not configured. |
| 25–30 | Params | `owner=user` selects user-level OAuth (Notion requirement). |
| 30 | `generate_oauth_state()` | CSRF state without PKCE verifier. |
| 35–49 | `exchange_code_for_token()` | Trades authorization code for tokens via JSON POST + Basic auth. |
| 37–42 | Headers | Basic auth with client ID/secret; JSON content type. |
| 44–48 | Payload | Standard authorization_code grant with redirect URI. |
| 52–65 | `refresh_access_token()` | Refresh token grant with same Basic auth headers. |
| 68–79 | `store_oauth_token()` | Saves tokens plus Notion workspace metadata. |
| 75–76 | `workspace_id`, `workspace_name` | Extra fields from Notion token response. |
| 82–89 | `get_notion_access_token()` | OAuth token from store, else static `notion_api_key` setting. |
| 92–109 | `refresh_notion_token_if_needed()` | Same refresh pattern as Google/Outlook modules. |

---

## Key Functions and Constants

| Name | Description |
|------|-------------|
| `NOTION_AUTH_URL` | `https://api.notion.com/v1/oauth/authorize` |
| `NOTION_TOKEN_URL` | `https://api.notion.com/v1/oauth/token` |
| `PROVIDER` | Token store key: `"notion"` |
| `build_authorization_url()` | Returns Notion authorization redirect URL |
| `exchange_code_for_token(code, **_kwargs)` | Accepts ignored kwargs for registry compatibility |
| `refresh_access_token(refresh_token)` | Gets new access token from refresh token |
| `store_oauth_token(token_response)` | Persists merged token + workspace info |
| `get_notion_access_token()` | Returns OAuth or static API key token |
| `refresh_notion_token_if_needed()` | Valid access token for Notion API calls |

---

## Notion-Specific Behavior

| Aspect | Spoon implementation |
|--------|---------------------|
| Client authentication | HTTP Basic (`Authorization: Basic base64(id:secret)`) |
| Token request body | JSON (`exchange_token_json`) |
| Authorization param | `owner=user` |
| PKCE | Not used |
| Static fallback | `settings.notion_api_key` if no OAuth token in store |
| Extra stored fields | `workspace_id`, `workspace_name` |

---

## Design Choices & Tradeoffs

| Choice | Advantage | Drawback | Alternative |
|--------|-----------|----------|-------------|
| Basic auth for token endpoint | Matches Notion API docs | Differs from form-based Google/Outlook | Notion-only helper in `oauth.py` (already done) |
| No PKCE | Notion flow doesn't require it in Spoon | Less defense-in-depth vs PKCE-capable flows | Add PKCE if Notion supports it for your app type |
| API key fallback in `get_notion_access_token` | Supports internal integration tokens without OAuth | Two auth modes complicate connector logic | OAuth-only |
| `**_kwargs` on exchange | Compatible with routes passing `pkce_verifier` | Silently ignores PKCE | Explicit unused parameter |
| Stale token on refresh failure | Graceful degradation | May fail Notion API with expired token | Surface error to user |
| Workspace metadata in store | Useful for multi-workspace debugging | Extra PII in token file | Store only tokens |

---

## Security Considerations

- **Basic auth encodes client secret** — only over HTTPS; never log Authorization headers.
- **Integration API key fallback** — long-lived secret in env; prefer OAuth for user-scoped access where possible.
- **State parameter** — CSRF protection via `state.py`; no PKCE for Notion in current code.
- **Workspace metadata** — `workspace_name` may identify customer orgs; protect token store encryption.
- **Refresh tokens** — persist with encryption; revoke in Notion admin if compromised.

---

## When and How to Extend

### Configure OAuth

Set:

- `SPOON_NOTION_CONNECTION_CLIENT_ID`
- `SPOON_NOTION_CONNECTION_SECRET_ID`
- `SPOON_NOTION_OAUTH_REDIRECT_URI`

Register redirect URI in Notion integration settings.

### Use integration token only (no OAuth)

Set `SPOON_NOTION_API_KEY`; `get_notion_access_token()` returns it when no OAuth token stored.

### Add bot vs user OAuth

Notion uses `owner=user` today; changing ownership model requires Notion dashboard configuration and param updates.

### Extend stored metadata

Pass additional keys in `merge_oauth_token(..., extra={...})` inside `store_oauth_token`.

### Testing

See `tests/test_security.py` for patterns using `notion_oauth` and token store.

---

## Environment variables (via settings)

| Setting property | Typical env prefix |
|------------------|-------------------|
| `notion_connection_client_id` | `SPOON_NOTION_CONNECTION_CLIENT_ID` |
| `notion_connection_secret_id` | `SPOON_NOTION_CONNECTION_SECRET_ID` |
| `notion_oauth_redirect_uri` | `SPOON_NOTION_OAUTH_REDIRECT_URI` |
| `notion_api_key` | `SPOON_NOTION_API_KEY` |
| `notion_oauth_configured` | Computed from client ID + secret |
