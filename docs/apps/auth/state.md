# `state.py` — OAuth CSRF State and PKCE Verifier Storage

`state.py` manages short-lived OAuth `state` parameters used to prevent CSRF attacks during authorization redirects. It optionally stores PKCE code verifiers alongside each state token so they can be retrieved securely at callback time. State can live in process memory (default) or Redis for multi-instance deployments.

> **Updated during the July 2026 security audit follow-up:** removed `validate_oauth_state()` and `consume_pkce_verifier()`. Both were unused dead code that internally called `pop_oauth_state()` — since `pop_oauth_state` **consumes** (deletes) the state on first read, calling any of these helpers a second time on the same state would always return "not found." Keeping multiple destructive, single-use wrappers around was a footgun waiting for a future caller to trigger a double-pop bug. `app/routes.py` already calls `pop_oauth_state()` directly, which remains the one and only supported way to validate + consume an OAuth state.

---

## Role in Spoon Architecture

When a user starts OAuth (`GET /auth/{provider}`), the provider module generates a random `state` value and redirects the browser to the external authorization server. When the user returns (`GET /auth/{provider}/callback`), Spoon must verify that the `state` query parameter matches a value Spoon recently issued.

```
User clicks "Connect Google"
        │
        ▼
build_authorization_url() ──▶ generate_oauth_state(pkce_verifier=...)
        │                              │
        │                              ▼
        │                     Stored in memory or Redis
        ▼
Redirect to Google with ?state=...
        │
        ▼
Google redirects back with ?state=...&code=...
        │
        ▼
auth_provider_callback() ──▶ pop_oauth_state(state)
        │                              │
        │                              ▼
        │                     Returns PKCE verifier (if any)
        ▼
exchange_code_for_token(code, pkce_verifier=...)
```

`pop_oauth_state` is called from `app/routes.py`. `generate_oauth_state` is called from provider modules (directly or via `oauth.py` re-export).

---

## Dependencies

### What this module imports

| Import | Source | Purpose |
|--------|--------|---------|
| `logging`, `secrets`, `time` | stdlib | Logging, cryptographically secure random tokens, timestamps |
| `dataclass` | stdlib | `_PendingState` data container |
| `get_settings` | `app.config` | Read `oauth_state_backend`, `redis_url` |
| `redis` | third-party (optional) | Redis backend when configured |

### What imports this module

| Consumer | Symbols used |
|----------|----------------|
| `app/auth/oauth.py` | `generate_oauth_state` (re-exported) |
| `app/routes.py` | `pop_oauth_state` |
| `tests/test_security.py` | `STATE_TTL_SECONDS`, `generate_oauth_state`, `pop_oauth_state` |

---

## Line-by-Line Reference

| Lines | Code / Section | Explanation |
|-------|----------------|-------------|
| 1–4 | Imports | Standard library modules for logging, secure randomness, time, and dataclasses. |
| 6 | `from app.config import get_settings` | Loads Spoon settings (backend choice, Redis URL). |
| 8 | `logger = logging.getLogger("spoon")` | Module logger for Redis import failures. |
| 10 | `STATE_TTL_SECONDS = 600` | State tokens expire after 10 minutes (OAuth best practice window). |
| 11 | `MAX_PENDING_STATES = 1000` | In-memory cap to prevent unbounded growth if pruning fails. |
| 13–17 | `@dataclass class _PendingState` | Internal record: creation time + optional PKCE verifier string. |
| 20 | `_pending_states: dict[str, _PendingState] = {}` | In-memory store mapping state token → pending entry. |
| 21 | `_redis_client = None` | Lazy singleton for Redis connection. |
| 24–40 | `_get_redis()` | Returns Redis client if `SPOON_OAUTH_STATE_BACKEND=redis` and URL is set; else `None`. |
| 29–31 | Backend check | Only connects to Redis when explicitly configured. |
| 33–37 | Import guard | Logs error if Redis backend chosen but `redis` package missing. |
| 39 | `redis.from_url(..., decode_responses=True)` | Creates client; strings returned instead of bytes. |
| 43–58 | `_prune_expired()` | Removes expired entries and enforces `MAX_PENDING_STATES` by dropping oldest. |
| 61–75 | `generate_oauth_state()` | Creates 32-byte URL-safe token; stores entry with optional PKCE verifier. |
| 62 | `secrets.token_urlsafe(32)` | Cryptographically secure, URL-safe random state (~43 chars). |
| 65–69 | Redis path | Stores hash `oauth:state:{state}` with TTL; fields: `created_at`, `pkce_verifier`. |
| 71–74 | Memory path | Prunes expired, then stores in `_pending_states` dict. |
| 78–99 | `pop_oauth_state()` | **Consumes** state (one-time use): deletes from store and returns entry or `None`. This is the **only** state-consuming function in the module now. |
| 80–92 | Redis pop | `HGETALL` + `DELETE`; reconstructs `_PendingState`; treats empty verifier as `None`. |
| 94–99 | Memory pop | Pops from dict; rejects if expired even if still present. |

`validate_oauth_state()` and `consume_pkce_verifier()` were removed — see the note at the top of this document.

---

## Key Functions and Types

| Name | Kind | Description |
|------|------|-------------|
| `STATE_TTL_SECONDS` | Constant (`600`) | Maximum age of a state token in seconds. |
| `MAX_PENDING_STATES` | Constant (`1000`) | Max in-memory pending states before oldest are evicted. |
| `_PendingState` | Dataclass | `created_at: float`, `pkce_verifier: str \| None`. |
| `generate_oauth_state` | Function | Creates state token; stores metadata; returns state string for URL. |
| `pop_oauth_state` | Function | Validates and removes state; returns `_PendingState` or `None`. This is the single supported entry point for consuming a state value. |

---

## Design Choices & Tradeoffs

| Choice | Advantage | Drawback | Alternative |
|--------|-----------|----------|-------------|
| Default in-memory backend | Zero dependencies; works for single-process dev | State lost on restart; not shared across workers | Always require Redis |
| Redis optional via settings | Horizontal scaling when needed | Two code paths to maintain and test | External session store only |
| One-time `pop` semantics | Prevents replay of callback URLs | Cannot validate state twice (by design) | Mark-used flag instead of delete |
| PKCE verifier stored with state | Verifier never sent to browser; retrieved at callback | Tighter coupling between state and PKCE | Separate verifier store |
| `MAX_PENDING_STATES` eviction | Protects against memory exhaustion | Legitimate bursts >1000 concurrent OAuth starts may fail | Redis-only for production |
| Empty string → `None` for verifier | Redis hash fields are strings; normalizes "no PKCE" | Slight special-case logic | Omit field when no PKCE |
| Single consuming function (`pop_oauth_state`) instead of multiple wrappers | Removes any risk of double-pop bugs from redundant helpers | Callers needing just a boolean or just the verifier must destructure the returned `_PendingState` themselves | Keep convenience wrappers but implement them as non-destructive peeks |

---

## Security Considerations

- **CSRF protection**: The random `state` parameter ensures callbacks belong to flows Spoon initiated. Attackers cannot forge callbacks without knowing a valid recent state.
- **One-time use**: `pop_oauth_state` deletes the entry immediately, preventing replay attacks with the same callback URL.
- **TTL (10 min)**: Limits the window for stolen state tokens to be used.
- **PKCE verifier secrecy**: The verifier is stored server-side only (memory/Redis), not in the redirect URL. Only the challenge goes to the authorization server.
- **Redis security**: If using Redis, protect network access and use TLS/authentication on the Redis URL in production.
- **Single consuming call per flow**: Only call `pop_oauth_state()` once per OAuth callback (as `app/routes.py` does). There is no longer a second wrapper function that could accidentally be called on the same state and silently fail because the entry was already consumed.

---

## When and How to Extend

### Enable Redis for multi-worker deployments

Set environment variables:

- `SPOON_OAUTH_STATE_BACKEND=redis`
- `SPOON_REDIS_URL=redis://...`

Install the `redis` Python package.

### Add a new OAuth provider with PKCE

In `build_authorization_url()`:

```python
verifier, challenge = generate_pkce_pair()
params["state"] = generate_oauth_state(pkce_verifier=verifier)
params["code_challenge"] = challenge
params["code_challenge_method"] = "S256"
```

The callback route already passes `state_entry.pkce_verifier` to `exchange_code_for_token`.

### Add a provider without PKCE

Call `generate_oauth_state()` with no arguments (Notion, Slack pattern).

### Adjust TTL

Change `STATE_TTL_SECONDS` and ensure Redis `expire` uses the same value (it reads the constant).

### Add a third backend (e.g. database)

Extend `_get_redis()` pattern: add settings flag, implement store/retrieve/delete in `generate_oauth_state` and `pop_oauth_state` branches.
