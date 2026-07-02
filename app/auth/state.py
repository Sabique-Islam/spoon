import secrets

_pending_states: set[str] = set()


def generate_oauth_state() -> str:
    state = secrets.token_urlsafe(32)
    _pending_states.add(state)
    return state


def validate_oauth_state(state: str) -> bool:
    if state in _pending_states:
        _pending_states.discard(state)
        return True
    return False
