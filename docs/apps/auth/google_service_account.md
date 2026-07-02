# `google_service_account.py` — Google Service Account Token Fallback

`google_service_account.py` loads a Google Cloud service account JSON key from disk and obtains a short-lived access token using the same OAuth scopes as Google Drive/Gmail OAuth. It provides an alternative authentication path when user OAuth is unavailable but a service account key is configured.

---

## Role in Spoon Architecture

Spoon's primary Google auth path is user OAuth via `gdrive_oauth.py`. For deployments that prefer domain-wide delegation or server-to-server access, this module reads a service account file and refreshes credentials on demand.

```
Connector needs Google API access
        │
        ├── User OAuth path: refresh_gdrive_token_if_needed()  [gdrive_oauth]
        │
        └── Fallback path: service_account_token()  [this module]
                    │
                    └── Uses GOOGLE_SCOPE_LIST from gdrive_oauth
```

Used by:

- `app/connectors/gdrive.py` — `service_account_token()`, `has_service_account_fallback()` (via `gdrive_oauth`)
- `app/connectors/gmail.py` — `service_account_token()`, `has_service_account_fallback()`

`gdrive_oauth.has_service_account_fallback()` delegates here to avoid circular imports at module load time.

---

## Dependencies

### What this module imports

| Import | Source | Purpose |
|--------|--------|---------|
| `logging` | stdlib | Error logging for missing packages |
| `Path` | `pathlib` | Resolve service account file path |
| `GOOGLE_SCOPE_LIST` | `app.auth.gdrive_oauth` | Same scopes as OAuth (Drive + Gmail readonly) |
| `get_settings` | `app.config` | `gdrive_service_account_path`, `gdrive_api_key` |

### What imports this module

| Consumer | Symbols used |
|----------|----------------|
| `app/auth/gdrive_oauth.py` | `has_service_account_fallback` (lazy import) |
| `app/connectors/gdrive.py` | `service_account_token`, `has_service_account_fallback` |
| `app/connectors/gmail.py` | `service_account_token`, `has_service_account_fallback` |

---

## Line-by-Line Reference

| Lines | Code / Section | Explanation |
|-------|----------------|-------------|
| 1–2 | Imports | Logging and pathlib. |
| 4 | `from app.auth.gdrive_oauth import GOOGLE_SCOPE_LIST` | Reuses OAuth scope list for consistency. |
| 5 | `from app.config import get_settings` | Settings for key file path. |
| 7 | `logger = logging.getLogger("spoon")` | Module logger. |
| 10–16 | `get_service_account_path()` | Returns path to JSON key file if it exists, else `None`. |
| 12 | `settings.gdrive_service_account_path or settings.gdrive_api_key` | Two setting names; second is legacy/alternate env name for path. |
| 15–16 | `path.is_file()` | Ensures path points to an existing file, not a directory or missing path. |
| 19–20 | `has_service_account_fallback()` | Boolean: is service account file configured and present? |
| 23–43 | `service_account_token()` | Loads credentials, refreshes, returns access token string or `None`. |
| 28–36 | Import guard | Requires `google-auth` and `requests`; logs install hint if missing. |
| 38–41 | Credential load | `Credentials.from_service_account_file` with `GOOGLE_SCOPE_LIST`. |
| 42 | `credentials.refresh(Request())` | Synchronous HTTP call to Google token endpoint. |
| 43 | `return credentials.token` | Short-lived bearer token for API calls. |

---

## Key Functions

| Function | Returns | Description |
|----------|---------|-------------|
| `get_service_account_path()` | `Path \| None` | Resolved filesystem path to service account JSON, if valid. |
| `has_service_account_fallback()` | `bool` | Whether service account auth is available. |
| `service_account_token()` | `str \| None` | Fresh access token from service account, or `None` on failure. |

---

## Configuration

| Setting / env | Purpose |
|---------------|---------|
| `SPOON_GDRIVE_SERVICE_ACCOUNT_PATH` | Primary path to service account JSON key file |
| `SPOON_GDRIVE_API_KEY` | Alternate setting name checked if primary unset (despite name, used as file path here) |

Required pip packages when using this module: `google-auth`, `requests`.

---

## Design Choices & Tradeoffs

| Choice | Advantage | Drawback | Alternative |
|--------|-----------|----------|-------------|
| Separate from OAuth module | Clear server-to-server vs user-delegated paths | Circular import avoided via lazy import in `gdrive_oauth` | Single unified Google auth class |
| Reuse `GOOGLE_SCOPE_LIST` | OAuth and service account always request same permissions | Creates import dependency on `gdrive_oauth` | Duplicate scope list constant |
| Sync `refresh()` inside async app | Simple google-auth API usage | Blocks event loop briefly during token fetch | Run in executor or use async google auth |
| Two settings for same path | Backward compatibility with `gdrive_api_key` name | Confusing naming (`api_key` is a file path) | Deprecate legacy setting |
| Returns `None` on all failures | Callers fall back gracefully | Silent failure unless caller checks logs | Raise explicit exceptions |
| No token caching in module | Always fresh token | Extra Google token requests per call | Cache with expiry like OAuth store |

---

## Security Considerations

- **Service account JSON is highly sensitive** — equivalent to a long-lived credential. Restrict file permissions (`0600`) and never commit to git.
- **Scopes are readonly** (`drive.readonly`, `gmail.readonly`) — limits damage if key leaks, but leaked keys still expose user/domain data accessible to the SA.
- **Domain-wide delegation** — if enabled in Google Workspace, the SA can impersonate users; configure Google Admin carefully.
- **Token not persisted** — access tokens are fetched in memory each call; no encryption layer here, but tokens are short-lived.
- **Legacy `gdrive_api_key` setting name** — avoid storing actual API keys in this path; it expects a JSON key file path.

---

## When and How to Extend

### Enable service account fallback

1. Create a Google Cloud service account with Drive/Gmail readonly access (or domain-wide delegation as needed).
2. Download JSON key to a secure path on the Spoon host.
3. Set `SPOON_GDRIVE_SERVICE_ACCOUNT_PATH=/path/to/key.json`.
4. Connectors will use `has_service_account_fallback()` to choose auth strategy.

### Add scopes

Update `GOOGLE_SCOPE_LIST` in `gdrive_oauth.py` (single source of truth for Google scopes).

### Cache service account tokens

Add module-level cache with expiry timestamp (similar to `token_utils.expires_at`) to reduce Google token endpoint traffic.

### Support workload identity / metadata server

Extend `service_account_token()` to use `google.auth.default()` when no file path is set (GCE/GKE environments).
