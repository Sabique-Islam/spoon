# `store.py` — Encrypted OAuth Token Persistence

`store.py` reads and writes OAuth tokens to a JSON file on disk, with optional Fernet encryption and restrictive file permissions. Each connected provider (e.g. `gdrive`, `notion`) has a keyed entry in the token store. Connectors and OAuth modules use this as the single source of truth for stored credentials.

> **Updated during the July 2026 security audit follow-up:**
> 1. Logs a one-time `WARNING` when tokens are being stored in **plaintext** (no `SPOON_TOKEN_ENCRYPTION_KEY` set), instead of failing silently.
> 2. `load_tokens()` no longer crashes the whole app with an uncaught `JSONDecodeError` if the file is corrupted or was encrypted with a key that has since changed — it now logs `CRITICAL` and returns an empty token set (forces re-authentication instead of 500 errors on every request).
> 3. The temp file used during atomic writes is now created with `0600` permissions from the moment it's opened (via `os.open`), removing a brief window where a freshly written file could be more permissive than intended before the final `chmod`.

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

| Section | Code | Explanation |
|-------|----------------|-------------|
| Imports | `json`, `logging`, `os`, `Path`, `Any` | Unchanged |
| `_fernet = None` | Lazy singleton for Fernet cipher | Unchanged |
| `_warned_plaintext = False` | **New** module-level flag | Ensures the plaintext-storage warning is logged once per process, not on every `save_tokens`/`load_tokens` call |
| `_store_path()` | Resolves path; `mkdir(parents=True, exist_ok=True, mode=0o700)` then an explicit `os.chmod(path.parent, 0o700)` | **Hardened.** `mkdir`'s `mode` argument is subject to the process umask, so it alone doesn't guarantee `0700` — the explicit `chmod` closes that gap. |
| `_get_fernet()` | Returns Fernet instance if `token_encryption_key` set; else logs a one-time warning and returns `None` (plaintext mode) | **New warning branch**: `if not settings.token_encryption_key: log warning once; return None` |
| Import guard | Logs if `cryptography` missing when encryption requested | Unchanged |
| `_encrypt(data)` | Encrypts string if Fernet available; otherwise returns plaintext | Unchanged |
| `_decrypt(data)` | Returns decrypted string, or **`None`** on failure (previously returned the raw ciphertext bytes as a fallback) | **Changed return type**: `str \| None`. `None` now clearly signals "could not decrypt," rather than silently handing back garbage that would later blow up `json.loads`. |
| `_set_permissions(path)` | Sets file `0600`, parent dir `0700` | Unchanged |
| `load_tokens()` | Reads file; detects Fernet prefix `gAAAA`; decrypts if needed; parses JSON | **Rewritten error handling** (see below) |
| Decrypt failure path | If `_decrypt` returns `None` (wrong/rotated key, corrupted ciphertext) | Logs `CRITICAL` and returns `{}` instead of propagating the old ciphertext into `json.loads` (which used to raise an **uncaught** `JSONDecodeError`) |
| JSON parse failure path | `try: json.loads(raw) except json.JSONDecodeError` | **New.** Any corrupted (non-JSON) file — encrypted or not — now degrades to "no tokens" with a `CRITICAL` log line, instead of a 500 on every request that touches tokens |
| `save_tokens(tokens)` | Atomic write: JSON → encrypt → write via `os.open(tmp, ..., 0o600)` → `fdopen`/write → `tmp.replace(path)` → `_set_permissions(path)` | **Hardened.** The temp file is created with `0600` from the start (via low-level `os.open`) instead of `Path.write_text` (which uses the default umask-derived mode), removing the brief window where the temp file could be more permissive before the final chmod. On any exception during write, the temp file is cleaned up (`tmp.unlink(missing_ok=True)`) and the exception re-raised. |
| `get_provider_token(provider)` | Loads full store, returns one provider's dict or `None` | Unchanged |
| `set_provider_token(provider, token_data)` | Merge-update one provider entry and save | Unchanged |
| `delete_provider_token(provider)` | Removes provider key and saves (disconnect) | Unchanged |

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
| Fail-soft to empty store on decrypt/parse failure | App stays up; user just needs to reconnect providers instead of a hard crash | Could mask a real corruption issue if the `CRITICAL` log isn't monitored | Fail hard (500) on decrypt error |
| Provider-keyed dict | One file for all integrations | Entire file rewritten on any token update | Separate file per provider |
| One-time plaintext-storage warning | Operators are alerted without log spam on every request | Warning is easy to miss if logs aren't reviewed at startup | Refuse to start without encryption key in production |

---

## Security Considerations

- **Set `SPOON_TOKEN_ENCRYPTION_KEY` in production** — generate with `Fernet.generate_key()`. Without it, tokens are stored in plaintext JSON, and Spoon now logs a `WARNING` (once, from `_get_fernet`) plus a startup `WARNING` from `app/main.py` telling you exactly this.
- **File permissions `0600`/`0700`** — limits access to the process owner; still protect the host filesystem and backups. The permission-setting race on first write has been closed (temp file is created with `0600` from the start).
- **Token file path** — default `.data/tokens.json`; keep outside web-served directories.
- **No in-memory caching** — every `get_provider_token` reads from disk (fresh data, but ensure disk is not synced from untrusted sources).
- **Refresh tokens are long-lived secrets** — treat the token file like a password vault.
- **Backup encryption** — if backing up `.data/`, encrypt backups separately.
- **Corrupted/undecryptable store fails soft** — if the encryption key changes or the file is corrupted, `load_tokens()` returns `{}` and logs `CRITICAL` rather than crashing every endpoint that reads a token. Operators should alert on `CRITICAL` log lines from this module, since it means all connected providers effectively got disconnected and users need to re-authenticate.

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
