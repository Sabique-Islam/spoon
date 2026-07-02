import os

import pytest

os.environ.setdefault("SPOON_RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("SPOON_ENV", "development")

from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


get_settings.cache_clear()
