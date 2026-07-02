import os

os.environ.setdefault("SPOON_RATE_LIMIT_ENABLED", "false")

from app.config import get_settings

get_settings.cache_clear()
