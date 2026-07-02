# `app/core/__init__.py`

**Source:** [`app/core/__init__.py`](../../app/core/__init__.py)  
**Lines:** 0 (empty file)

## Purpose

Marks `app/core/` as a Python package so submodules (`errors`, `security`, `sync_state`) can be imported as `app.core.errors`, etc.

## Role in the stack

| Aspect | Detail |
| --- | --- |
| Runtime behavior | **None** — no code executes |
| Import path | Enables `from app.core.security import ...` |
| Public API | Not used as a barrel export; callers import submodules directly |

## Line-by-line reference

| Lines | Code | Behavior |
| --- | --- | --- |
| — | *(empty)* | No symbols defined; package exists by directory + this file |

## Design choices

| Choice | Advantage | Drawback |
| --- | --- | --- |
| Empty `__init__.py` | Clear submodule boundaries; no hidden re-exports | No single `from app.core import X` shortcut |
| No `__all__` | Avoids maintaining duplicate export list | Discoverability relies on docs/IDE |

## When to modify

Add content here **only** if you intentionally want a stable re-export surface, e.g.:

```python
from app.core.errors import sanitize_sync_errors
from app.core.security import require_api_key

__all__ = ["sanitize_sync_errors", "require_api_key"]
```

Until then, leave the file empty to match current project conventions.
