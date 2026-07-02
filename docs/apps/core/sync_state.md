# `app/core/sync_state.py`

**Source:** [`app/core/sync_state.py`](../../app/core/sync_state.py)  
**Lines:** 35

## Purpose

Persists incremental sync cursors per provider on disk so connectors can resume from the last successful position (timestamps, page tokens, history IDs) across process restarts.

## Role in the stack

| Function | Typical use |
| --- | --- |
| `load_sync_state` | Read full state dict |
| `get_provider_cursor` | Read one cursor key for a provider |
| `set_provider_cursor` | Atomically update one cursor key |

State file lives alongside the token store directory (see path logic below).

## Dependencies

| Import | Purpose |
| --- | --- |
| `json` | Serialize state to disk |
| `Path` | Filesystem paths and atomic write |
| `get_settings` | `token_store_path` for base directory |

## File layout

| Item | Path |
| --- | --- |
| Token store (config) | `SPOON_TOKEN_STORE_PATH` default `.data/tokens.json` |
| Sync state file | `{parent of token_store}/sync_state.json` |
| Temp write | `sync_state.tmp` → atomic replace |

Example structure:

```json
{
  "gmail": {
    "history_id": "12345"
  },
  "slack": {
    "channel:C123": "1700000000.000100"
  }
}
```

## Line-by-line reference

| Lines | Code | Behavior |
| --- | --- | --- |
| 1–3 | Imports | json, Path, typing |
| 5 | `get_settings` | Config for token store path |
| 8–12 | `_state_path()` | Ensures parent dir exists; returns `sync_state.json` path |
| 9–10 | Base dir | `Path(settings.token_store_path).parent` |
| 11 | `mkdir(parents=True, exist_ok=True)` | Creates `.data/` if missing |
| 12 | Return path | `base / "sync_state.json"` |
| 15–18 | `load_sync_state()` | Read JSON or `{}` if missing |
| 16 | Get path | Via `_state_path()` |
| 17–18 | Missing file | Empty dict |
| 19 | Parse | `json.loads(path.read_text())` |
| 22–24 | `get_provider_cursor()` | Nested lookup |
| 23 | Load state | Full dict |
| 24 | Return | `(state.get(provider) or {}).get(key)` or None |
| 27–34 | `set_provider_cursor()` | Read-modify-write |
| 28–29 | Load existing | Full state dict |
| 30 | `setdefault(provider, {})` | Ensure provider subdict |
| 31 | Assign key | `provider_state[key] = value` |
| 32–33 | Atomic write | Write `.tmp` then `replace()` |
| 34 | `tmp.replace(path)` | POSIX atomic rename over target |

## Tradeoffs

| Choice | Benefit | Cost |
| --- | --- | --- |
| JSON file | Human-readable, easy backup | Not safe for high concurrent writers |
| Atomic replace | Crash-safe single-writer updates | Last write wins under concurrency |
| Colocated with tokens | One `.data/` directory | Couples sync state path to token path setting |
| String cursors only | Simple API | Callers must serialize complex cursors |
| No locking | Simple code | Multiple workers can corrupt state |

## Security notes

- Sync state may reveal which integrations are connected and activity timestamps — restrict filesystem permissions on `.data/`.
- Do not store secrets in cursor values; use auth token store instead.
- Backup `sync_state.json` with tokens when migrating deployments.

## Extension guide

1. **Per-user state:** Namespace top-level keys by user ID if multi-tenant.
2. **Redis backend:** Mirror API with GET/SET on `spoon:sync:{provider}:{key}`.
3. **Migration:** Version key in JSON (`"_version": 1`) for schema changes.
4. **Clear cursor:** Add `delete_provider_cursor(provider, key)` for full resync flows.
5. **Decouple path:** Add `SPOON_SYNC_STATE_PATH` in config instead of deriving from token path.

## Related documentation

- [config.md](../config.md) — `token_store_path`
- Connectors (see [connectors/](../connectors/)) — call `get_provider_cursor` / `set_provider_cursor` during sync
