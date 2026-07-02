import json
from pathlib import Path
from typing import Any

from app.config import get_settings


def _state_path() -> Path:
    settings = get_settings()
    base = Path(settings.token_store_path).parent
    base.mkdir(parents=True, exist_ok=True)
    return base / "sync_state.json"


def load_sync_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def get_provider_cursor(provider: str, key: str) -> str | None:
    state = load_sync_state()
    return (state.get(provider) or {}).get(key)


def set_provider_cursor(provider: str, key: str, value: str) -> None:
    path = _state_path()
    state = load_sync_state()
    provider_state = state.setdefault(provider, {})
    provider_state[key] = value
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)
