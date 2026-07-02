# `providers.py` — OAuth Provider Registry

`providers.py` defines the central registry of OAuth integrations Spoon supports. Each provider is described by an `OAuthProviderSpec` dataclass that wires together configuration checks, authorization URL building, token exchange, storage, and user-facing success messages. FastAPI routes iterate this registry instead of hardcoding provider names.

---

## Role in Spoon Architecture

`app/routes.py` implements generic OAuth endpoints:

- `GET /auth/{provider}` — start OAuth
- `GET /auth/{provider}/callback` — complete OAuth
- `DELETE /auth/{provider}` — disconnect

All three use `OAUTH_PROVIDERS` from this module:

```
HTTP /auth/notion
        │
        ▼
OAUTH_PROVIDERS["notion"]  ──▶ OAuthProviderSpec
        │
        ├── configured(settings) ──▶ env vars set?
        ├── build_authorization_url()
        ├── exchange_code_for_token(code, pkce_verifier=...)
        └── store_oauth_token(response)
```

Adding a new integration requires a new spec function and a registry entry — routes stay unchanged.

---

## Dependencies

### What this module imports

| Import | Source | Purpose |
|--------|--------|---------|
| `dataclass` | stdlib | Frozen `OAuthProviderSpec` |
| `Any`, `Awaitable`, `Callable`, `Protocol` | `typing` | Type definitions for provider callables |
| `Settings` | `app.config` | Type for `configured` callback |
| Provider modules | lazy imports inside `_*_spec()` | Avoid loading all OAuth code at startup |

### What imports this module

| Consumer | Symbols used |
|----------|----------------|
| `app/routes.py` | `OAUTH_PROVIDERS` |

---

## Line-by-Line Reference

| Lines | Code / Section | Explanation |
|-------|----------------|-------------|
| 1–4 | Imports | Dataclass and typing utilities; `Settings` type. |
| 7–12 | `OAuthModule` Protocol | Documents expected provider module interface (not enforced at runtime for registry). |
| 8 | `build_authorization_url() -> str` | Sync function returning redirect URL. |
| 9–11 | `exchange_code_for_token` | Async; accepts optional `pkce_verifier`. |
| 12 | `store_oauth_token` | Async; persists token response. |
| 15–23 | `OAuthProviderSpec` dataclass | Immutable bundle of provider metadata and callables. |
| 16 | `name: str` | Provider key (matches URL segment and token store key). |
| 17 | `configured: Callable[[Settings], bool]` | Whether required env vars are present. |
| 18 | `env_hint: str` | Human-readable env var names for error messages. |
| 19–22 | Callable fields | Bound functions from provider modules. |
| 23 | `success_message: str` | Returned to client after successful OAuth callback. |
| 26–37 | `_notion_spec()` | Builds spec for Notion; lazy-imports `notion_oauth`. |
| 40–51 | `_gdrive_spec()` | Google Drive + Gmail OAuth spec. |
| 54–65 | `_slack_spec()` | Slack OAuth spec. |
| 68–79 | `_outlook_spec()` | Microsoft Outlook OAuth spec. |
| 82–87 | `OAUTH_PROVIDERS` dict | Maps provider name → spec instance. |

---

## Key Types and Registry

### `OAuthProviderSpec` fields

| Field | Type | Role |
|-------|------|------|
| `name` | `str` | Provider identifier (`notion`, `gdrive`, `slack`, `outlook`) |
| `configured` | `(Settings) → bool` | Settings property check before starting OAuth |
| `env_hint` | `str` | Shown in HTTP 400 when not configured |
| `build_authorization_url` | `() → str` | Creates provider authorization URL |
| `exchange_code_for_token` | `async (code, *, pkce_verifier?) → dict` | Trades code for tokens |
| `store_oauth_token` | `async (dict) → None` | Saves tokens to store |
| `success_message` | `str` | JSON response message on success |

### `OAUTH_PROVIDERS` registry

| Key | Module | `configured` checks | PKCE |
|-----|--------|----------------------|------|
| `notion` | `notion_oauth` | `notion_oauth_configured` | No |
| `gdrive` | `gdrive_oauth` | `gdrive_oauth_configured` | Yes |
| `slack` | `slack_oauth` | `slack_oauth_configured` | No |
| `outlook` | `outlook_oauth` | `outlook_oauth_configured` | Yes |

---

## Design Choices & Tradeoffs

| Choice | Advantage | Drawback | Alternative |
|--------|-----------|----------|-------------|
| Registry dict vs plugin discovery | Explicit, easy to grep | Must edit this file for new providers | Entry points / auto-discovery |
| Lazy imports in spec builders | Faster app import; avoids circular deps | Slight delay on first access per provider | Top-level imports |
| Frozen dataclass spec | Immutable registry entries | Cannot patch at runtime easily | Plain dict |
| `Protocol` for documentation | Clear contract for new modules | Not validated automatically | ABC base class |
| Separate `configured` + `build_*` checks | HTTP layer can fail early with env hint | Duplicate config checks in provider modules | Single validation function |
| Function references not classes | Minimal boilerplate | No shared base class behavior | `OAuthProvider` class hierarchy |

---

## Security Considerations

- **Registry exposes provider names** — only known keys in `OAUTH_PROVIDERS` are valid; unknown providers return 404 from routes.
- **All OAuth routes require API key** (`require_api_key` in routes) — prevents unauthorized OAuth initiation on a exposed Spoon instance.
- **PKCE support is per-provider** — registry does not enforce PKCE; security depends on each provider module using state + PKCE where appropriate.
- **`env_hint` strings** — help operators configure secrets without exposing actual values.

---

## When and How to Extend

### Add a new OAuth provider (e.g. `linear`)

1. Create `app/auth/linear_oauth.py` with:
   - `build_authorization_url()`
   - `async exchange_code_for_token(code, *, pkce_verifier=None)`
   - `async store_oauth_token(token_response)`
   - Token getters/refresh helpers for connectors

2. Add settings in `app/config.py`:
   - `linear_oauth_configured` property
   - Client ID, secret, redirect URI fields

3. Add spec builder and registry entry:

```python
def _linear_spec() -> OAuthProviderSpec:
    from app.auth import linear_oauth
    return OAuthProviderSpec(
        name="linear",
        configured=lambda s: s.linear_oauth_configured,
        env_hint="SPOON_LINEAR_CLIENT_ID and SPOON_LINEAR_CLIENT_SECRET",
        build_authorization_url=linear_oauth.build_authorization_url,
        exchange_code_for_token=linear_oauth.exchange_code_for_token,
        store_oauth_token=linear_oauth.store_oauth_token,
        success_message="Linear connected successfully",
    )

OAUTH_PROVIDERS = {
    ...
    "linear": _linear_spec(),
}
```

4. Register connector in `app/connectors/registry.py` if sync is needed.

5. No changes required in `routes.py` if provider name matches registry key.

### Update success messages or env hints

Edit the relevant `_*_spec()` function only.

### Enforce provider interface statically

Replace `Protocol` with an abstract base class and have provider modules inherit it (larger refactor).
