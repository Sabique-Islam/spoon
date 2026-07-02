import logging
import secrets
import time
from dataclasses import dataclass

from app.config import get_settings

logger = logging.getLogger("spoon")

STATE_TTL_SECONDS = 600
MAX_PENDING_STATES = 1000


@dataclass
class _PendingState:
    created_at: float
    pkce_verifier: str | None = None


_pending_states: dict[str, _PendingState] = {}
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    settings = get_settings()
    if settings.oauth_state_backend != "redis" or not settings.redis_url:
        return None

    try:
        import redis
    except ImportError:
        logger.error("redis package required for SPOON_OAUTH_STATE_BACKEND=redis")
        return None

    _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def _prune_expired() -> None:
    now = time.time()
    expired = [
        state
        for state, entry in _pending_states.items()
        if now - entry.created_at > STATE_TTL_SECONDS
    ]
    for state in expired:
        _pending_states.pop(state, None)

    if len(_pending_states) > MAX_PENDING_STATES:
        oldest = sorted(
            _pending_states.items(), key=lambda item: item[1].created_at
        )
        for state, _ in oldest[: len(_pending_states) - MAX_PENDING_STATES]:
            _pending_states.pop(state, None)


def generate_oauth_state(*, pkce_verifier: str | None = None) -> str:
    state = secrets.token_urlsafe(32)
    client = _get_redis()

    if client:
        payload = {"created_at": time.time(), "pkce_verifier": pkce_verifier or ""}
        client.hset(f"oauth:state:{state}", mapping=payload)
        client.expire(f"oauth:state:{state}", STATE_TTL_SECONDS)
        return state

    _prune_expired()
    _pending_states[state] = _PendingState(
        created_at=time.time(), pkce_verifier=pkce_verifier
    )
    return state


def pop_oauth_state(state: str) -> _PendingState | None:
    client = _get_redis()
    if client:
        key = f"oauth:state:{state}"
        data = client.hgetall(key)
        if not data:
            return None
        client.delete(key)
        verifier = data.get("pkce_verifier") or None
        if verifier == "":
            verifier = None
        return _PendingState(
            created_at=float(data.get("created_at", time.time())),
            pkce_verifier=verifier,
        )

    entry = _pending_states.pop(state, None)
    if not entry:
        return None
    if time.time() - entry.created_at > STATE_TTL_SECONDS:
        return None
    return entry


def validate_oauth_state(state: str) -> bool:
    return pop_oauth_state(state) is not None


def consume_pkce_verifier(state: str) -> str | None:
    entry = pop_oauth_state(state)
    if not entry:
        return None
    return entry.pkce_verifier
