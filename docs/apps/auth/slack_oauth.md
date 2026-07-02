# `slack_oauth.py` — Slack OAuth Integration

`slack_oauth.py` implements Slack's OAuth v2 install flow for obtaining a bot/user access token with a broad set of read-only scopes. Unlike Google or Outlook, Slack tokens in Spoon are stored without refresh-token rotation logic — the module also supports falling back to a pre-configured bot token from environment settings.

---

## Role in Spoon Architecture

Slack message sync (`app/connectors/slack.py`) calls `get_slack_access_token()` before Slack Web API requests. OAuth connect/disconnect uses the generic routes with provider key `slack`.

```
GET /auth/slack ──▶ build_authorization_url()
        │
GET /auth/slack/callback ──▶ exchange_code_for_token ──▶ store_oauth_token
        │
Slack sync ──▶ get_slack_access_token()
        │
        └── fallback: settings.slack_bot_token
```

Registered in `OAUTH_PROVIDERS` with message "Slack connected successfully".

---

## Dependencies

### What this module imports

| Import | Source | Purpose |
|--------|--------|---------|
| `typing.Any` | stdlib | Type hints |
| `urlencode` | `urllib.parse` | Authorization URL encoding |
| `httpx` | third-party | Direct token exchange HTTP (not via `oauth.exchange_token_form`) |
| `generate_oauth_state` | `app.auth.oauth` | CSRF state |
| `get_provider_token`, `set_provider_token` | `app.auth.store` | Token persistence |
| `get_settings` | `app.config` | Slack client credentials, redirect, bot token fallback |

### What imports this module

| Consumer | Symbols used |
|----------|----------------|
| `app/auth/providers.py` | OAuth registry functions |
| `app/connectors/slack.py` | `get_slack_access_token` |

**Note:** Does not use `token_utils.py` — no refresh-token merge pattern.

---

## Line-by-Line Reference

| Lines | Code / Section | Explanation |
|-------|----------------|-------------|
| 1–8 | Imports | urllib, httpx, oauth state, store, config. |
| 10–12 | Constants | Slack OAuth URLs and provider key `"slack"`. |
| 14–36 | `SLACK_SCOPES` | Comma-separated list of read-oriented Slack scopes for history, users, files, etc. |
| 39–50 | `build_authorization_url()` | Slack authorize URL with scopes and state. |
| 41–42 | Config guard | Raises if Slack OAuth env not configured. |
| 44–48 | Params | `client_id`, `scope`, `redirect_uri`, `state`. |
| 53–69 | `exchange_code_for_token()` | POST to `oauth.v2.access`; validates Slack `ok` field. |
| 62–65 | httpx POST | Form-encoded payload; 30s timeout. |
| 67–68 | Slack error handling | Raises `ValueError` with Slack `error` code if `ok` is false. |
| 72–83 | `store_oauth_token()` | Custom dict shape (not `merge_oauth_token`). |
| 73 | `team = token_response.get("team") or {}` | Extracts workspace team metadata. |
| 77–81 | Stored fields | access_token, bot_user_id, team_id, team_name, scope |
| 86–93 | `get_slack_access_token()` | Stored OAuth token or env `slack_bot_token`. |

---

## Key Functions and Constants

| Name | Description |
|------|-------------|
| `SLACK_AUTH_URL` | `https://slack.com/oauth/v2/authorize` |
| `SLACK_TOKEN_URL` | `https://slack.com/api/oauth.v2.access` |
| `SLACK_SCOPES` | Comma-separated OAuth scopes (read-heavy) |
| `PROVIDER` | Token store key: `"slack"` |
| `build_authorization_url()` | Redirect URL to start Slack OAuth |
| `exchange_code_for_token(code, **_kwargs)` | Exchange code; raises on Slack API error |
| `store_oauth_token(token_response)` | Save Slack-specific token metadata |
| `get_slack_access_token()` | Token for Web API calls (OAuth or env fallback) |

---

## Slack OAuth Scopes (stored in `SLACK_SCOPES`)

Scopes include channel/group/IM history and read, users, files, pins, bookmarks, emoji, usergroups, reactions, and remote files — all read-oriented for indexing Slack content without posting messages.

| Scope category | Examples in list |
|----------------|------------------|
| Message history | `channels:history`, `groups:history`, `im:history` |
| Channel metadata | `channels:read`, `groups:read` |
| Users | `users:read`, `users:read.email`, `users.profile:read` |
| Workspace | `team:read` |
| Content | `files:read`, `pins:read`, `bookmarks:read`, `emoji:read` |

Adding scopes requires updating `SLACK_SCOPES` and re-installing the Slack app for workspaces.

---

## Stored Token Shape

```json
{
  "slack": {
    "access_token": "xoxb-...",
    "bot_user_id": "U...",
    "team_id": "T...",
    "team_name": "My Workspace",
    "scope": "channels:history,..."
  }
}
```

No `refresh_token`, `expires_at`, or refresh helpers in this module.

---

## Design Choices & Tradeoffs

| Choice | Advantage | Drawback | Alternative |
|--------|-----------|----------|-------------|
| No refresh logic | Slack bot tokens are often long-lived | Token rotation not handled automatically | Implement token rotation if Slack app requires it |
| Custom `store_oauth_token` | Captures Slack-specific team/bot fields | Inconsistent with other providers using `merge_oauth_token` | Extend merge with Slack extras |
| Direct httpx in exchange | Parses Slack `ok`/`error` JSON shape | Duplicates HTTP logic from `oauth.py` | Wrap Slack response validation in shared helper |
| Bot token env fallback | Simple ops for single-workspace deployments | Two auth paths | OAuth-only |
| Large scope list upfront | One install grants all read needs | Users may hesitate at broad permissions | Minimal scopes + incremental auth |
| No PKCE | Slack v2 OAuth often uses client secret server-side | Less PKCE protection | Add PKCE if Slack app type requires |

---

## Security Considerations

- **Bot tokens (`xoxb-`)** are powerful workspace credentials — encrypt token store at rest.
- **Broad read scopes** — compromised token exposes messages, files, and user emails across allowed conversations.
- **CSRF state** — still used via `generate_oauth_state()` on authorization URL.
- **Client secret** in token exchange POST — protect `SPOON_SLACK_CLIENT_SECRET`.
- **Env bot token fallback** — avoid committing `SPOON_SLACK_BOT_TOKEN` to version control.
- **No token expiry handling** — if Slack revokes token, sync fails until reconnect or env update.

---

## When and How to Extend

### Add OAuth connect for Slack

Configure:

- `SPOON_SLACK_CLIENT_ID`
- `SPOON_SLACK_CLIENT_SECRET`
- `SPOON_SLACK_OAUTH_REDIRECT_URI`

Add redirect URL to Slack app OAuth settings.

### Use bot token without OAuth

Set `SPOON_SLACK_BOT_TOKEN`; connector works without OAuth flow if token has required scopes.

### Add a scope

1. Append to `SLACK_SCOPES` list (comma-joined string).
2. Update Slack app manifest / OAuth scope list in Slack API dashboard.
3. Users disconnect and reconnect (`DELETE /auth/slack` then `GET /auth/slack`).

### Add refresh / rotation support

If Slack begins issuing expiring tokens for your app type:

1. Import `merge_oauth_token` and `token_needs_refresh`.
2. Add `refresh_access_token` and `refresh_slack_token_if_needed` mirroring `outlook_oauth.py`.
3. Update `app/connectors/slack.py` to call refresh helper.

### Improve error handling

Map Slack `error` codes (`invalid_code`, `bad_redirect_uri`) to clearer HTTP errors in routes or here.

---

## Environment variables (via settings)

| Setting property | Purpose |
|------------------|---------|
| `slack_client_id` | Slack app client ID |
| `slack_client_secret` | Slack app client secret |
| `slack_oauth_redirect_uri` | OAuth redirect URL |
| `slack_bot_token` | Optional static bot token fallback |
| `slack_oauth_configured` | True when client ID + secret set |
