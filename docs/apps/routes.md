# `app/routes.py`

**Source:** [`app/routes.py`](../../app/routes.py)  
**Lines:** 175

## Purpose

Defines the FastAPI `APIRouter` for all Spoon HTTP endpoints: health, provider listing, OAuth connect/disconnect, per-provider and bulk sync, and semantic search.

## Role in the stack

| Endpoint group | Auth | Function |
| --- | --- | --- |
| `/health` | None | Liveness |
| `/providers`, `/auth/*`, `/sync/*`, `/search` | `require_api_key` (if configured) | Core product API |
| OAuth callbacks | API key + OAuth state | Token exchange and storage |

Mounted at `/api/v1` from `main.py`.

## Dependencies

| Import | Module | Role |
| --- | --- | --- |
| `OAUTH_PROVIDERS` | `app.auth.providers` | OAuth spec registry |
| `pop_oauth_state` | `app.auth.state` | CSRF state validation |
| `delete_provider_token` | `app.auth.store` | Disconnect |
| `get_settings` | `app.config` | OAuth configuration checks |
| `SUPPORTED_PROVIDERS`, `get_connector` | `app.connectors.registry` | Sync targets |
| `sanitize_sync_errors` | `app.core.errors` | Safe error messages |
| `require_api_key` | `app.core.security` | Optional API key gate |
| `log_audit`, `log_search`, `log_sync` | `app.logging` | Structured logs |
| Pydantic models | `app.models` | Request/response schemas |
| `search_documents` | `app.supermemory.search` | Search backend |

## Endpoint reference

| Method | Path | Response | Description |
| --- | --- | --- | --- |
| `GET` | `/health` | `HealthResponse` | Always `{ "status": "ok" }` |
| `GET` | `/providers` | `ProvidersResponse` | Lists `SUPPORTED_PROVIDERS` |
| `GET` | `/auth/{provider}` | 302 redirect | Starts OAuth flow |
| `GET` | `/auth/{provider}/callback` | JSON status | Completes OAuth |
| `DELETE` | `/auth/{provider}` | JSON status | Removes stored token |
| `POST` | `/sync/{provider}` | `SyncResponse` | Sync one provider |
| `POST` | `/sync/all` | `list[SyncResponse]` | Sync all authenticated providers |
| `POST` | `/search` | `SearchResponse` | Supermemory document search |

## Line-by-line reference

| Lines | Code | Behavior |
| --- | --- | --- |
| 1–3 | stdlib imports | Logging, timing, typing |
| 5–6 | FastAPI imports | Router, Depends, HTTPException, RedirectResponse |
| 8–23 | Internal imports | Auth, connectors, errors, security, logging, models, search |
| 25–26 | Logger and router | Module-level `APIRouter()` |
| 29–31 | `health()` | Unauthenticated health check |
| 34–36 | `providers()` | Returns connector names; requires API key when configured |
| 39–57 | `auth_provider()` | Validates provider, OAuth config, builds auth URL, 302 redirect |
| 41–43 | Unknown provider | 404 with `{ "error": "Unknown provider: ..." }` |
| 45–50 | Not configured | 400 with env hint from OAuth spec |
| 51–56 | `build_authorization_url` failure | 400 generic OAuth not configured |
| 60–100 | `auth_provider_callback()` | OAuth callback handler |
| 68–70 | Unknown provider | 404 |
| 72–77 | OAuth `error` param | 400 authorization denied |
| 79–82 | Missing `code` | 400 |
| 84–86 | Invalid/missing state | 400 invalid OAuth state |
| 88–97 | Token exchange | Calls spec methods; 400 on any exception |
| 99–100 | Success | Audit log + JSON success message |
| 103–109 | `disconnect_provider()` | Deletes token; audit log |
| 112–138 | `_run_sync()` | Internal sync orchestration |
| 113–114 | Unknown provider | 404 |
| 116–121 | Not authenticated | 401 |
| 123–125 | Timing + `connector.sync()` | Measures duration |
| 126–132 | Logging | `log_sync` + `log_audit` |
| 134–138 | Response | Sanitized errors in `SyncResponse` |
| 141–143 | `sync_provider()` | Public wrapper for `_run_sync` |
| 146–160 | `sync_all()` | Skips unauthenticated; 401 if none connected |
| 163–174 | `search()` | Calls Supermemory; 502 on failure; logs duration |

## Sync flow (internal)

```
POST /sync/{provider}
  → get_connector(provider)
  → connector.is_authenticated()
  → connector.sync()  → documents + errors
  → sanitize_sync_errors()
  → SyncResponse
```

## Tradeoffs

| Choice | Benefit | Cost |
| --- | --- | --- |
| API key on OAuth callback | Protects callback URL from anonymous abuse | OAuth user agent must send API key (unusual for browser flows) |
| `_run_sync` helper | Shared logic for single and bulk sync | Raises HTTPException from helper (not ideal layering) |
| `sync_all` skips unauthenticated | Partial success without errors | Silent skip — caller may not know which were skipped |
| Search errors → 502 | Distinguishes upstream failure | Client cannot tell config vs network vs API errors |
| Generic OAuth exchange errors | No token leakage | Hard to debug from client alone |

## Security notes

- All sensitive routes use `Depends(require_api_key)` when `SPOON_API_KEY` is set.
- OAuth state is validated via `pop_oauth_state` (one-time use).
- Sync errors are sanitized before JSON response (see [core/errors.md](./core/errors.md)).
- OAuth denial logged at WARNING; token exchange failures at EXCEPTION with server logs.
- Audit logs omit fields named `token`, `secret`, `password` (see [logging.md](./logging.md)).
- Health endpoint is intentionally public for load balancers.

## Extension guide

1. **New provider sync:** Register in `connectors/registry.py`; no route change if name is in `SUPPORTED_PROVIDERS`.
2. **New OAuth provider:** Add to `OAUTH_PROVIDERS`; routes are already parameterized by `{provider}`.
3. **Async background sync:** Return 202 from route and enqueue job; keep `_run_sync` as worker entry.
4. **Search filters:** Extend `SearchRequest` model and pass filters to `search_documents`.
5. **Rate limits:** Adjust prefixes in [core/security.md](./core/security.md) `RATE_LIMITS`.
6. **Webhook-style auth:** Add separate router without `require_api_key` for provider signatures (Slack).

## Related documentation

- [models.md](./models.md) — request/response types
- [core/security.md](./core/security.md) — API key dependency
- [core/errors.md](./core/errors.md) — error sanitization
- [supermemory/search.md](./supermemory/search.md) — search implementation
- [auth/providers.md](./auth/providers.md) — OAuth registry (when documented)
- [connectors/registry.md](./connectors/registry.md) — connector registry (when documented)
