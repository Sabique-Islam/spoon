# `app/config.py`

**Source:** [`app/config.py`](../../app/config.py)  
**Lines:** 104

## Purpose

Central configuration for Spoon using Pydantic Settings. Reads environment variables and optional `.env` file, validates types, exposes computed OAuth redirect URIs and feature flags, and provides a cached singleton accessor.

> **Updated during the July 2026 security audit follow-up:** added `rate_limit_backend`, `trust_proxy_headers`, and `cors_allowed_origins` (+ `cors_origins_list` property) to support distributed rate limiting, safe-by-default proxy header handling, and explicit opt-in CORS.

## Role in the stack

| Concern | How `config.py` handles it |
| --- | --- |
| Secrets & API keys | Typed fields with `SPOON_` prefix |
| OAuth readiness | `*_oauth_configured` properties |
| Sync/search limits | Numeric caps (`max_*`, `sync_since_days`) |
| Deployment | `env`, `app_url`, `is_production` |
| Caching | `@lru_cache` on `get_settings()` |

## Dependencies

| Import | Purpose |
| --- | --- |
| `functools.lru_cache` | Single `Settings` instance per process |
| `pydantic_settings.BaseSettings` | Env var loading and validation |
| `SettingsConfigDict` | `.env` file, prefix, ignore unknown keys |

No internal app imports — this module is a leaf dependency.

## Environment variable mapping

All fields map to `SPOON_<FIELD_NAME_UPPER>` (e.g. `SPOON_SUPERMEMORY_API_KEY`). Boolean and int coercion is handled by Pydantic.

| Field | Default | Required | Description |
| --- | --- | --- | --- |
| `supermemory_api_key` | — | **Yes** | Supermemory API key |
| `api_key` | `None` | No | If set, protects API with `X-API-Key` / Bearer |
| `env` | `"development"` | No | `"production"` disables OpenAPI UI |
| `linear_api_key` | `None` | No | Linear API token |
| `notion_api_key` | `None` | No | Notion integration token |
| `notion_connection_client_id` | `None` | No | Notion OAuth client ID |
| `notion_connection_secret_id` | `None` | No | Notion OAuth secret |
| `notion_connection_authorization_url` | `None` | No | Override redirect URI |
| `gdrive_api_key` | `None` | No | Google Drive API key (limited use) |
| `gdrive_service_account_path` | `None` | No | Path to service account JSON |
| `gdrive_connection_client_id` | `None` | No | Google OAuth client ID |
| `gdrive_connection_secret_id` | `None` | No | Google OAuth client secret |
| `gdrive_connection_authorization_url` | `None` | No | Override redirect URI |
| `slack_app_id` | `None` | No | Slack app ID |
| `slack_client_id` | `None` | No | Slack OAuth client ID |
| `slack_client_secret` | `None` | No | Slack OAuth client secret |
| `slack_signing_secret` | `None` | No | Slack request signing |
| `slack_verification_token` | `None` | No | Legacy Slack verification |
| `slack_bot_token` | `None` | No | Bot token for API calls |
| `slack_connection_authorization_url` | `None` | No | Override redirect URI |
| `outlook_connection_client_id` | `None` | No | Microsoft OAuth client ID |
| `outlook_connection_secret_id` | `None` | No | Microsoft OAuth secret |
| `outlook_connection_authorization_url` | `None` | No | Override redirect URI |
| `token_encryption_key` | `None` | No | Fernet key for token encryption at rest |
| `oauth_state_backend` | `"memory"` | No | OAuth CSRF state storage backend |
| `redis_url` | `None` | No | Redis URL when using Redis state backend |
| `app_url` | `"http://localhost:8000"` | No | Public base URL for OAuth callbacks |
| `container_tag` | `"spoon"` | No | Supermemory container tag for isolation |
| `notion_version` | `"2022-06-28"` | No | Notion API-Version header |
| `token_store_path` | `".data/tokens.json"` | No | OAuth token persistence path |
| `max_block_depth` | `10` | No | Notion block tree depth cap |
| `max_content_length` | `100_000` | No | Max text content per document |
| `max_documents_per_sync` | `5000` | No | Sync batch ceiling |
| `max_file_bytes` | `25_000_000` | No | Max upload size for file ingest |
| `sync_since_days` | `None` | No | Optional lookback window for sync |
| `max_slack_channels` | `500` | No | Slack channel enumeration cap |
| `max_slack_messages_per_channel` | `2000` | No | Messages per channel cap |
| `rate_limit_enabled` | `True` | No | Toggle rate limiting entirely |
| `rate_limit_backend` | `"memory"` | No | **New.** `"memory"` (per-process) or `"redis"` (shared across workers/replicas, reuses `redis_url`) |
| `trust_proxy_headers` | `False` | No | **New.** Only honor `X-Forwarded-For` for rate-limit client identification when `True` — enable only behind a reverse proxy that overwrites this header itself |
| `cors_allowed_origins` | `None` | No | **New.** Comma-separated list of allowed browser origins. Empty/unset = no `CORSMiddleware` added, cross-origin browser requests stay blocked (current default behavior, now explicit) |

## Line-by-line reference

| Lines | Code | Behavior |
| --- | --- | --- |
| 1 | `from functools import lru_cache` | Process-wide settings cache |
| 3–4 | Pydantic settings imports | Base class and config dict |
| 6–9 | `Settings` + `model_config` | Load `.env`, prefix `SPOON_`, ignore extra env keys |
| 11 | `supermemory_api_key: str` | Required; app fails at startup if missing |
| 12 | `api_key: str \| None` | Optional API auth; `None` = open API |
| 13 | `env: str` | Environment name string |
| 14–48 | Provider and limit fields | See table above |
| 50–52 | `is_production` | True when `env.lower() == "production"` |
| 54–58 | `notion_oauth_configured` | Both client ID and secret must be set |
| 60–64 | `notion_oauth_redirect_uri` | Explicit URL or `{app_url}/api/v1/auth/notion/callback` |
| 66–70 | `gdrive_oauth_configured` | Google OAuth credentials present |
| 72–76 | `gdrive_oauth_redirect_uri` | Default `/api/v1/auth/gdrive/callback` |
| 78–80 | `slack_oauth_configured` | Slack client ID + secret |
| 82–86 | `slack_oauth_redirect_uri` | Default `/api/v1/auth/slack/callback` |
| 88–92 | `outlook_oauth_configured` | Microsoft OAuth credentials |
| 94–98 | `outlook_oauth_redirect_uri` | Default `/api/v1/auth/outlook/callback` |
| **New** | `cors_origins_list` property | Splits `cors_allowed_origins` on commas, strips whitespace, drops empties; returns `[]` when unset |
| 101–103 | `get_settings()` | `@lru_cache` returns singleton `Settings()` |

## Tradeoffs

| Choice | Benefit | Cost |
| --- | --- | --- |
| `extra="ignore"` | Safe deployment with unrelated env vars | Typos in `SPOON_*` names fail silently |
| Optional `api_key` | Easy local dev without auth | Production misconfiguration leaves API open |
| Redirect URI override fields | Supports proxy/CDN callback URLs | Mis-set URL breaks OAuth |
| `@lru_cache` on getter | No repeated env parsing | Cannot reload config without restart |
| Single `.env` path | Simple local setup | No multi-file env layering |

## Security notes

- `supermemory_api_key` is required at startup — ensures ingest/search cannot run unconfigured.
- Store secrets only in environment or `.env`; never commit `.env`.
- `token_encryption_key` should be a Fernet key when encrypting tokens at rest (see auth store).
- When `api_key` is unset, all routes using `require_api_key` become publicly accessible. `app/main.py` now logs a `WARNING` (and `CRITICAL` if `env=production`) at startup in this case.
- OAuth redirect URIs must exactly match provider console registration.
- `trust_proxy_headers` defaults to `False` (safe) — only set to `True` behind a reverse proxy that itself sets/overwrites `X-Forwarded-For`; otherwise the rate limiter becomes trivially bypassable.
- `rate_limit_backend="redis"` requires `redis_url` to be set and the `redis` package installed (already in `requirements.txt`); falls back to in-memory with a logged error if misconfigured.
- `cors_allowed_origins` is opt-in; leaving it unset preserves the existing (safe) default of no CORS middleware at all.

## Extension guide

1. **Add a new setting:** Add a typed field on `Settings`; document in `.env.example` as `SPOON_YOUR_FIELD`.
2. **Add OAuth provider config:** Add `*_connection_*` fields plus `*_oauth_configured` and `*_oauth_redirect_uri` properties following existing patterns.
3. **Add computed flags:** Use `@property` methods that derive from multiple fields (see Notion/Slack examples).
4. **Testing:** Use `get_settings.cache_clear()` in tests after overriding env vars.
5. **Validation:** Add `@field_validator` or `@model_validator` on `Settings` for cross-field rules.

## Related documentation

- [main.md](./main.md) — uses `is_production`
- [core/security.md](./core/security.md) — `api_key`, `rate_limit_enabled`
- [supermemory/client.md](./supermemory/client.md) — `supermemory_api_key`, `container_tag`
- [core/sync_state.md](./core/sync_state.md) — `token_store_path` parent directory
