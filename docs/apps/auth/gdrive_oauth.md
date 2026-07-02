# `gdrive_oauth.py` — Google Drive and Gmail OAuth

`gdrive_oauth.py` implements the full OAuth 2.0 flow for Google APIs used by Spoon: Google Drive (readonly) and Gmail (readonly). It uses PKCE, offline access with refresh tokens, and integrates with the shared token store and refresh utilities. Connectors call `refresh_gdrive_token_if_needed()` before Google API requests.

---

## Role in Spoon Architecture

Google is a shared auth domain for two connectors:

- `app/connectors/gdrive.py` — Google Drive files
- `app/connectors/gmail.py` — Gmail messages

Both use the same OAuth provider key `gdrive` in the token store. The registry entry in `providers.py` advertises this as "Google connected successfully (Drive + Gmail)".

```
GET /auth/gdrive ──▶ build_authorization_url() ──▶ Google consent
        │
GET /auth/gdrive/callback ──▶ exchange_code_for_token ──▶ store_oauth_token
        │
Sync ──▶ refresh_gdrive_token_if_needed() ──▶ Google APIs
        │
        └── (optional) service_account_token() via google_service_account.py
```

Also exports `GOOGLE_SCOPE_LIST` / `GOOGLE_SCOPES` for service account fallback.

---

## Dependencies

### What this module imports

| Import | Source | Purpose |
|--------|--------|---------|
| `typing.Any` | stdlib | Type hints |
| `urlencode` | `urllib.parse` | Build authorization query string |
| `httpx` | third-party | HTTP errors on refresh failure |
| `exchange_token_form`, `generate_oauth_state` | `app.auth.oauth` | Token POST and CSRF state |
| `generate_pkce_pair` | `app.auth.pkce` | PKCE verifier/challenge |
| `get_provider_token`, `set_provider_token` | `app.auth.store` | Token persistence |
| `merge_oauth_token`, `token_needs_refresh` | `app.auth.token_utils` | Merge and refresh timing |
| `get_settings` | `app.config` | Google client credentials and redirect URI |

### What imports this module

| Consumer | Symbols used |
|----------|----------------|
| `app/auth/providers.py` | All OAuth flow functions (via registry) |
| `app/auth/google_service_account.py` | `GOOGLE_SCOPE_LIST` |
| `app/connectors/gdrive.py` | `has_service_account_fallback`, `refresh_gdrive_token_if_needed` |
| `app/connectors/gmail.py` | `refresh_gdrive_token_if_needed` |
| `tests/test_security.py` | Module-level tests |

---

## Line-by-Line Reference

| Lines | Code / Section | Explanation |
|-------|----------------|-------------|
| 1–10 | Imports | Standard, HTTP, and Spoon auth/config modules. |
| 12–20 | Constants | Google OAuth endpoints, scopes, provider key `"gdrive"`. |
| 14–17 | `GOOGLE_SCOPE_LIST` | Drive readonly + Gmail readonly scopes. |
| 18–19 | `GOOGLE_SCOPES`, `GDRIVE_SCOPES` | Space-joined scope string for authorization URL. |
| 23–40 | `build_authorization_url()` | Builds Google authorization URL with PKCE and offline consent. |
| 25–26 | Config check | Raises `ValueError` if OAuth env vars missing. |
| 28 | `generate_pkce_pair()` | Creates verifier (stored in state) and challenge (in URL). |
| 29–39 | Query params | Standard OAuth2 + Google-specific: `access_type=offline`, `prompt=consent` for refresh token. |
| 36 | `generate_oauth_state(pkce_verifier=verifier)` | CSRF state with PKCE verifier stored server-side. |
| 40 | Return full URL | `{GDRIVE_AUTH_URL}?{urlencode(params)}` |
| 43–56 | `exchange_code_for_token()` | Authorization code → token response via form POST. |
| 54–55 | PKCE | Adds `code_verifier` to payload when present. |
| 59–67 | `refresh_access_token()` | Uses refresh token grant. |
| 70–78 | `store_oauth_token()` | Merges response and saves under `PROVIDER` key. |
| 81–85 | `get_gdrive_access_token()` | Returns stored access token without refresh. |
| 88–91 | `has_service_account_fallback()` | Lazy import to `google_service_account` (breaks circular import). |
| 94–111 | `refresh_gdrive_token_if_needed()` | Main entry for connectors; refreshes if expired. |
| 97–98 | No refresh token | Returns current access token or None. |
| 100–101 | OAuth not configured | Uses existing access token only (no refresh attempt). |
| 103–104 | `token_needs_refresh` | Skips refresh if still valid. |
| 106–111 | Refresh attempt | On `httpx.HTTPError`, returns stale access token (graceful degradation). |

---

## Key Functions and Constants

| Name | Kind | Description |
|------|------|-------------|
| `GDRIVE_AUTH_URL` | Constant | Google authorization endpoint |
| `GDRIVE_TOKEN_URL` | Constant | Google token endpoint |
| `GOOGLE_SCOPE_LIST` | Constant | List of OAuth scope URLs |
| `PROVIDER` | Constant | `"gdrive"` — token store key |
| `build_authorization_url` | Function | Start OAuth; returns redirect URL |
| `exchange_code_for_token` | Async function | Exchange auth code for tokens |
| `refresh_access_token` | Async function | Refresh using stored refresh token |
| `store_oauth_token` | Async function | Persist merged token dict |
| `get_gdrive_access_token` | Async function | Read access token from store |
| `has_service_account_fallback` | Function | Whether service account JSON is configured |
| `refresh_gdrive_token_if_needed` | Async function | Get valid access token for API calls |

---

## Google-Specific OAuth Parameters

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `access_type` | `offline` | Request refresh token |
| `prompt` | `consent` | Force consent screen so refresh token is issued |
| `code_challenge_method` | `S256` | PKCE SHA-256 challenge |
| `scope` | Drive + Gmail readonly | Limits Spoon to read-only access |

---

## Design Choices & Tradeoffs

| Choice | Advantage | Drawback | Alternative |
|--------|-----------|----------|-------------|
| Single provider for Drive + Gmail | One OAuth consent for both connectors | Provider name `gdrive` is Gmail-confusing | Separate OAuth apps per product |
| `prompt=consent` every time | More reliable refresh token on re-auth | Users see consent screen each connect | `prompt` only on first connect |
| Stale token on refresh HTTP error | Sync may still work briefly | May use expired token and get 401 | Fail hard and force re-auth |
| Lazy import for service account | Avoids circular import with `google_service_account` | Indirection | Move scopes to shared constants file |
| Client secret in token refresh | Required for Google confidential clients | Secret in server memory during requests | Public client + PKCE only (Google supports both) |

---

## Security Considerations

- **Readonly scopes only** — cannot modify Drive files or send email via these scopes.
- **PKCE + state** — CSRF and authorization code interception mitigations.
- **Refresh tokens** stored encrypted if `SPOON_TOKEN_ENCRYPTION_KEY` is set.
- **Client secret** in env (`SPOON_GDRIVE_CONNECTION_SECRET_ID`) — protect like any OAuth client secret.
- **Service account fallback** — separate credential with its own risk profile; see `google_service_account.md`.

---

## When and How to Extend

### Add a Google scope (e.g. Calendar)

1. Append scope URL to `GOOGLE_SCOPE_LIST`.
2. Users must disconnect and re-authorize (`prompt=consent`) to grant new scope.
3. Update service account usage if fallback should include new scope.

### Change redirect URI

Set `SPOON_GDRIVE_OAUTH_REDIRECT_URI` in config to match Google Cloud Console OAuth client.

### Add write scope (not recommended without review)

Changing from readonly to read/write increases blast radius; update connector behavior and documentation accordingly.

### Debugging refresh failures

Check logs for `httpx.HTTPError`; verify refresh token still valid (user revoked access, etc.). User must re-run `GET /auth/gdrive`.

### Environment variables

| Variable | Purpose |
|----------|---------|
| `SPOON_GDRIVE_CONNECTION_CLIENT_ID` | OAuth client ID |
| `SPOON_GDRIVE_CONNECTION_SECRET_ID` | OAuth client secret |
| `SPOON_GDRIVE_OAUTH_REDIRECT_URI` | Callback URL registered with Google |

Configured when `settings.gdrive_oauth_configured` is true.
