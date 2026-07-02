from functools import lru_cache

from supermemory import Supermemory

from app.config import get_settings


@lru_cache
def get_supermemory_client() -> Supermemory:
    settings = get_settings()
    return Supermemory(api_key=settings.supermemory_api_key)
