# Spoon `app/` documentation index

Exhaustive module-level reference for the Spoon FastAPI application under [`app/`](../../app/).

Each page covers **purpose**, **role**, **dependencies**, a **line-range code table**, **tradeoffs**, **security notes**, and an **extension guide**.

**Start here for a hands-on flow:** [Example walkthrough (OAuth → sync → search)](../WALKTHROUGH.md)

---

## Root application modules

| Module | Source | Documentation |
| --- | --- | --- |
| Entry point | [`app/main.py`](../../app/main.py) | [main.md](./main.md) |
| Configuration | [`app/config.py`](../../app/config.py) | [config.md](./config.md) |
| Pydantic schemas | [`app/models.py`](../../app/models.py) | [models.md](./models.md) |
| HTTP routes | [`app/routes.py`](../../app/routes.py) | [routes.md](./routes.md) |
| Logging | [`app/logging.py`](../../app/logging.py) | [logging.md](./logging.md) |

---

## Core (`app/core/`)

| Module | Source | Documentation |
| --- | --- | --- |
| Error sanitization | [`app/core/errors.py`](../../app/core/errors.py) | [core/errors.md](./core/errors.md) |
| API key & rate limits | [`app/core/security.py`](../../app/core/security.py) | [core/security.md](./core/security.md) |
| Sync cursors | [`app/core/sync_state.py`](../../app/core/sync_state.py) | [core/sync_state.md](./core/sync_state.md) |
| Package marker | [`app/core/__init__.py`](../../app/core/__init__.py) | [core/__init__.md](./core/__init__.md) |

---

## HTTP (`app/http/`)

| Module | Source | Documentation |
| --- | --- | --- |
| Retry client | [`app/http/retry_client.py`](../../app/http/retry_client.py) | [http/retry_client.md](./http/retry_client.md) |

---

## Supermemory (`app/supermemory/`)

| Module | Source | Documentation |
| --- | --- | --- |
| SDK client factory | [`app/supermemory/client.py`](../../app/supermemory/client.py) | [supermemory/client.md](./supermemory/client.md) |
| Document search | [`app/supermemory/search.py`](../../app/supermemory/search.py) | [supermemory/search.md](./supermemory/search.md) |
| Document ingest | [`app/supermemory/ingest.py`](../../app/supermemory/ingest.py) | [supermemory/ingest.md](./supermemory/ingest.md) |

---

## Auth (`app/auth/`)

OAuth, token storage, PKCE, and provider-specific authorization flows.

| Module | Source | Documentation |
| --- | --- | --- |
| Provider registry | [`app/auth/providers.py`](../../app/auth/providers.py) | [auth/providers.md](./auth/providers.md) |
| OAuth state (CSRF) | [`app/auth/state.py`](../../app/auth/state.py) | [auth/state.md](./auth/state.md) |
| Token persistence | [`app/auth/store.py`](../../app/auth/store.py) | [auth/store.md](./auth/store.md) |
| Shared OAuth helpers | [`app/auth/oauth.py`](../../app/auth/oauth.py) | [auth/oauth.md](./auth/oauth.md) |
| PKCE | [`app/auth/pkce.py`](../../app/auth/pkce.py) | [auth/pkce.md](./auth/pkce.md) |
| Token utilities | [`app/auth/token_utils.py`](../../app/auth/token_utils.py) | [auth/token_utils.md](./auth/token_utils.md) |
| Google service account | [`app/auth/google_service_account.py`](../../app/auth/google_service_account.py) | [auth/google_service_account.md](./auth/google_service_account.md) |
| Notion OAuth | [`app/auth/notion_oauth.py`](../../app/auth/notion_oauth.py) | [auth/notion_oauth.md](./auth/notion_oauth.md) |
| Google Drive OAuth | [`app/auth/gdrive_oauth.py`](../../app/auth/gdrive_oauth.py) | [auth/gdrive_oauth.md](./auth/gdrive_oauth.md) |
| Slack OAuth | [`app/auth/slack_oauth.py`](../../app/auth/slack_oauth.py) | [auth/slack_oauth.md](./auth/slack_oauth.md) |
| Outlook OAuth | [`app/auth/outlook_oauth.py`](../../app/auth/outlook_oauth.py) | [auth/outlook_oauth.md](./auth/outlook_oauth.md) |

---

## Connectors (`app/connectors/`)

Source integrations that fetch, normalize, and ingest content into Supermemory.

| Module | Source | Documentation |
| --- | --- | --- |
| Base connector | [`app/connectors/base.py`](../../app/connectors/base.py) | [connectors/base.md](./connectors/base.md) |
| Registry | [`app/connectors/registry.py`](../../app/connectors/registry.py) | [connectors/registry.md](./connectors/registry.md) |
| Text helpers | [`app/connectors/text.py`](../../app/connectors/text.py) | [connectors/text.md](./connectors/text.md) |
| Gmail | [`app/connectors/gmail.py`](../../app/connectors/gmail.py) | [connectors/gmail.md](./connectors/gmail.md) |
| Google Drive | [`app/connectors/gdrive.py`](../../app/connectors/gdrive.py) | [connectors/gdrive.md](./connectors/gdrive.md) |
| Drive content extraction | [`app/connectors/gdrive_content.py`](../../app/connectors/gdrive_content.py) | [connectors/gdrive_content.md](./connectors/gdrive_content.md) |
| Notion | [`app/connectors/notion.py`](../../app/connectors/notion.py) | [connectors/notion.md](./connectors/notion.md) |
| Slack | [`app/connectors/slack.py`](../../app/connectors/slack.py) | [connectors/slack.md](./connectors/slack.md) |
| Outlook | [`app/connectors/outlook.py`](../../app/connectors/outlook.py) | [connectors/outlook.md](./connectors/outlook.md) |
| Linear | [`app/connectors/linear.py`](../../app/connectors/linear.py) | [connectors/linear.md](./connectors/linear.md) |

---

## Request flow (high level)

```
Client
  → main.py (middleware: rate limit → request log)
  → routes.py (API key, handler)
  → connectors/* or supermemory/* or auth/*
  → Supermemory / external APIs
```

---

## Related project docs

- [WALKTHROUGH.md](../WALKTHROUGH.md) — end-to-end example (Gmail OAuth → sync → search)
- [docs/INIT.md](../INIT.md) — local environment setup

---

## Documentation coverage

| Area | Status |
| --- | --- |
| Root modules | Documented |
| `core/` | Documented |
| `http/` | Documented |
| `supermemory/` | Documented |
| `auth/` | Documented |
| `connectors/` | Documented |
