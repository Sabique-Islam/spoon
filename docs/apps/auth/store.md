# `store.py` — Encrypted OAuth Token Persistence

`store.py` reads and writes OAuth tokens to a JSON file on disk, with optional Fernet encryption and restrictive file permissions. Each connected provider (e.g. `gdrive`, `notion`) has a keyed entry in the token store. Connectors and OAuth modules use this as the single source of truth for stored credentials.

---

## Role in Spoon Architecture

Spoon persists OAuth tokens between restarts so users do not re-authorize on every sync. The token store sits at the bottom of the auth stack:

```
OAuth callback ──▶ provider.store_oauth_token() ──▶ set_provider_token()
                                                          │
Sync / API calls ◀── get_provider_token() ◀───────────────┘
                                                          │
                                              load_tokens() / save_tokens()
                                                          │
                                              .data/tokens.json (encrypted)
```

Disconnect flow (`DELETE /auth/{provider}`) calls `delete_provider_token`. Tests and security checks use `save_tokens` / `set_provider_token` directly.

---

## Dependencies

### What this module imports

| Import | Source | Purpose |
|--------|--------|---------|
| `json`, `logging`, `os` | stdlib | JSON serialization, logging, file permissions |
| `Path` | `pathlib` | Token file path handling |
| `Any` | `typing` | Flexible token dict typing |
| `get_settings` | `app.config` | `token_store_path`, `token_encryption_key` |
| `cryptography.fernet.Fernet` | third-party (optional) | Symmetric encryption when key is set |

### What imports this module

| Consumer | Symbols used |
|----------|----------------|
| `app/routes.py` | `delete_provider_token` |
| `app/auth/token_utils.py` | `get_provider_token` |
| `app/auth/gdrive_oauth.py` | `get_provider_token`, `set_provider_token` |
| `app/auth/notion_oauth.py` | `get_provider_token`, `set_provider_token` |
| `app/auth/slack_oauth.py` | `get_provider_token`, `set_provider_token` |
| `app/auth/outlook_oauth.py` | `get_provider_token`, `set_provider_token` |
| `app/connectors/gmail.py` | `get_provider_token` |
| `app/connectors/gdrive.py` | `get_provider_token` |
| `app/connectors/notion.py` | `get_provider_token` |
| `app/connectors/slack.py` | `get_provider_token` |
| `app/connectors/outlook.py` | `get_provider_token` |
| `tests/test_security.py` | `save_tokens`, `set_provider_token`, `get_provider_token` |

---

## Line-by-Line Reference

| Lines | Code / Section | Explanation |
|-------|----------------|-------------|
| 1–5 | Imports | JSON, logging, OS, pathlib, typing. |
| 7 | `from app.config import get_settings` | Settings for path and encryption key. |
| 9 | `logger = logging.getLogger("spoon")` | Logs encryption/decryption issues. |
| 11 | `_fernet = None` | Lazy singleton for Fernet cipher. |
| 14–17 | `_store_path()` | Resolves path from settings; creates parent dirs (`mkdir(parents=True)`). |
| 20–36 | `_get_fernet()` | Returns Fernet instance if `token_encryption_key` set; else `None` (plaintext mode). |
| 29–33 | Import guard | Logs if `cryptography` missing when encryption requested. |
| 35 | `Fernet(settings.token_encryption_key.encode())` | Key must be valid Fernet key (44-char url-safe base64). |
| 39–43 | `_encrypt(data)` | Encrypts string if Fernet available; otherwise returns plaintext. |
| 46–54 | `_decrypt(data)` | Decrypts string; on failure logs warning and treats as plaintext (migration path). |
| 50–54 | Decrypt fallback | Allows reading old plaintext files after enabling encryption, or corrupted data recovery attempt. |
| 57–62 | `_set_permissions(path)` | Sets file `0600`, parent dir `0700` (owner read/write only). |
| 61–62 | `except OSError: pass` | Ignores permission errors on platforms that restrict chmod. |
| 65–72 | `load_tokens()` | Reads file; detects Fernet prefix `gAAAA`; decrypts if needed; parses JSON. |
| 67–68 | Missing file | Returns empty dict (no providers connected). |
| 70–71 | Fernet detection | Encrypted payloads from Fernet start with `gAAAA` when base64-encoded. |
| 75–82 | `save_tokens(tokens)` | Atomic write: JSON → encrypt → write `.tmp` → rename replace. |
| 79–81 | Atomic replace | Reduces risk of corrupted half-written token file on crash. |
| 85–87 | `get_provider_token(provider)` | Loads full store, returns one provider's dict or `None`. |
| 90–93 | `set_provider_token(provider, token_data)` | Merge-update one provider entry and save. |
| 96–99 | `delete_provider_token(provider)` | Removes provider key and saves (disconnect). |

---

## Key Functions

| Function | Description |
|----------|-------------|
| `_store_path()` | Returns `Path` to token file; ensures parent directory exists. |
| `_get_fernet()` | Lazy-init Fernet cipher from settings, or `None`. |
| `_encrypt` / `_decrypt` | String-level encrypt/decrypt with plaintext passthrough. |
| `_set_permissions` | Restricts file/directory permissions to owner only. |
| `load_tokens()` | Load entire token dict from disk. |
| `save_tokens(tokens)` | Persist entire token dict atomically. |
| `get_provider_token(provider)` | Get one provider's token data. |
| `set_provider_token(provider, token_data)` | Upsert one provider's tokens. |
| `delete_provider_token(provider)` | Remove one provider from store. |

---

## Token Store Shape

The on-disk JSON is a top-level object keyed by provider name:

```json
{
  "gdrive": {
    "access_token": "...",
    "refresh_token": "...",
    "expires_at": 1234567890.0,
    "token_type": "Bearer"
  },
  "slack": {
    "access_token": "...",
    "team_id": "...",
    "team_name": "..."
  }
}
```

Exact fields vary by provider; see each `*_oauth.py` module.

---

## Design Choices & Tradeoffs

| Choice | Advantage | Drawback | Alternative |
|--------|-----------|----------|-------------|
| JSON file on disk | Simple, human-debuggable (when unencrypted), no DB dependency | Not suitable for high concurrency or multi-host without shared FS | PostgreSQL, Vault, cloud secret manager |
| Optional Fernet encryption | Protects tokens at rest when key is configured | Key management burden; plaintext if key unset | Always require encryption |
| Atomic tmp + replace | Avoids truncated files on crash | Two writes per save | Write-in-place with locking |
| Full-file read/write per op | Simple implementation | O(n) with store size; race if multiple processes | File locking or DB transactions |
| Plaintext fallback on decrypt failure | Easier migration / recovery | Could mask corruption or wrong key | Fail hard on decrypt error |
| Provider-keyed dict | One file for all integrations | Entire file rewritten on any token update | Separate file per provider |

---

## Security Considerations

- **Set `SPOON_TOKEN_ENCRYPTION_KEY` in production** — generate with `Fernet.generate_key()`. Without it, tokens are stored in plaintext JSON.
- **File permissions `0600`/`0700`** — limits access to the process owner; still protect the host filesystem and backups.
- **Token file path** — default `.data/tokens.json`; keep outside web-served directories.
- **No in-memory caching** — every `get_provider_token` reads from disk (fresh data, but ensure disk is not synced from untrusted sources).
- **Refresh tokens are long-lived secrets** — treat the token file like a password vault.
- **Backup encryption** — if backing up `.data/`, encrypt backups separately.

---

## When and How to Extend

### Enable encryption

1. `pip install cryptography`
2. Set `SPOON_TOKEN_ENCRYPTION_KEY` to a Fernet key
3. Existing plaintext file is encrypted on next `save_tokens`

### Change storage location

Set `SPOON_TOKEN_STORE_PATH` (maps to `settings.token_store_path`).

### Add fields for a new provider

Provider modules call `set_provider_token` with their dict shape; no changes needed in `store.py` unless you add validation.

### Migrate to external secret store

Replace `load_tokens`/`save_tokens` internals while keeping `get_provider_token` / `set_provider_token` / `delete_provider_token` API stable so connectors keep working.

### Add file locking for multi-process

Wrap read-modify-write in `fcntl` or `filelock` inside `set_provider_token` and `delete_provider_token`.
