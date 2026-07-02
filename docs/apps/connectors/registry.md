# `registry.py` — Connector Factory

## Purpose

`registry.py` is the single lookup table that maps provider name strings to connector classes. It exposes:

- **`CONNECTORS`** — dictionary of provider key → connector class
- **`SUPPORTED_PROVIDERS`** — ordered list of registered keys
- **`get_connector(provider)`** — factory that instantiates a connector by name

HTTP routes and CLI sync commands use this module to resolve `"slack"` → `SlackConnector()` without importing every connector at every call site.

## Architecture Role

```
API / CLI / sync runner
        │
        ▼
  get_connector("notion")
        │
        ▼
  CONNECTORS["notion"]  →  NotionConnector()
        │
        ▼
  connector.sync()  →  SyncResult
```

| Component | Role |
|-----------|------|
| `CONNECTORS` | Static registry of all supported providers |
| `SUPPORTED_PROVIDERS` | Derived list for `/providers` API responses |
| `get_connector` | Runtime factory with validation |

This is the only module that imports all connector implementations together, creating a deliberate central dependency hub.

## Dependencies

| Import | Module | Usage |
|--------|--------|-------|
| `Type` | `typing` | Type hint for connector class map |
| `Connector` | `app.connectors.base` | Protocol type for registry values |
| `GDriveConnector` | `app.connectors.gdrive` | Google Drive sync |
| `GmailConnector` | `app.connectors.gmail` | Gmail sync |
| `LinearConnector` | `app.connectors.linear` | Linear issues/projects |
| `NotionConnector` | `app.connectors.notion` | Notion pages |
| `OutlookConnector` | `app.connectors.outlook` | Microsoft Outlook mail |
| `SlackConnector` | `app.connectors.slack` | Slack workspace |

## Line-Range Reference

| Lines | Section | Description |
|-------|---------|-------------|
| 1–2 | Imports | `Type` and `Connector` protocol |
| 3–9 | Connector imports | All six provider connector classes |
| 11–18 | `CONNECTORS` dict | Maps provider string keys to classes |
| 20 | `SUPPORTED_PROVIDERS` | `list(CONNECTORS.keys())` |
| 23–27 | `get_connector` | Lookup, validate, instantiate |

## Functions and Classes

### `CONNECTORS`

| Key | Class |
|-----|-------|
| `"notion"` | `NotionConnector` |
| `"linear"` | `LinearConnector` |
| `"gdrive"` | `GDriveConnector` |
| `"gmail"` | `GmailConnector` |
| `"outlook"` | `OutlookConnector` |
| `"slack"` | `SlackConnector` |

### `SUPPORTED_PROVIDERS`

| Property | Value |
|----------|-------|
| Type | `list[str]` |
| Content | Keys of `CONNECTORS` in insertion order |
| Usage | Exposed via API as available sync targets |

### `get_connector(provider: str) -> Connector`

| Step | Behavior |
|------|----------|
| Lookup | `CONNECTORS.get(provider)` |
| Missing key | Raises `KeyError(f"Unknown provider: {provider}")` |
| Success | Returns `cls()` — new instance each call |

## Tradeoffs

### Pros

| Benefit | Detail |
|---------|--------|
| Single source of truth | One place to see all supported providers |
| Lazy instantiation | Connectors created only when sync is requested |
| Simple API | String key → ready-to-use connector |
| Protocol typing | Return type is `Connector`, not a concrete class |

### Cons

| Limitation | Detail |
|------------|--------|
| Eager imports | Importing registry loads all connector modules |
| Manual registration | New connectors require editing this file |
| No plugin discovery | Cannot add providers without code change |
| `KeyError` on unknown | Callers must catch or validate keys first |

### Alternatives

| Alternative | Trade-off |
|-------------|-----------|
| Entry-point plugins (`importlib.metadata`) | Dynamic discovery vs. complexity |
| Lazy import inside `get_connector` | Faster startup vs. scattered import logic |
| Enum for provider keys | Type safety vs. extra boilerplate |
| Dependency injection container | Testability vs. over-engineering for six providers |

## Security and Resource Notes

| Topic | Detail |
|-------|--------|
| No auth here | Registry only maps names; credentials checked in each connector |
| Instance per call | No shared mutable state between sync runs |
| Import side effects | Loading registry triggers import of all connector modules (and their deps) |

## Extension Guide

### Register a new provider

1. Implement connector class in `app/connectors/<name>.py` satisfying `Connector` protocol.
2. Add import at top of `registry.py`.
3. Add entry to `CONNECTORS`:

```python
from app.connectors.myprovider import MyProviderConnector

CONNECTORS: dict[str, Type[Connector]] = {
    # ... existing entries ...
    "myprovider": MyProviderConnector,
}
```

4. `SUPPORTED_PROVIDERS` updates automatically.
5. Add auth routes, env vars, and tests as needed.

### Validating provider names

Before calling `get_connector`, check membership:

```python
if provider not in CONNECTORS:
    raise HTTPException(404, f"Unknown provider: {provider}")
connector = get_connector(provider)
```

Or catch `KeyError` from `get_connector` and map to HTTP 404.

### Testing

Mock individual connectors by patching `CONNECTORS` or `get_connector` return value rather than importing the full registry when testing unrelated code.
