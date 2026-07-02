import logging
from pathlib import Path

from app.auth.gdrive_oauth import GOOGLE_SCOPE_LIST
from app.config import get_settings

logger = logging.getLogger("spoon")


def get_service_account_path() -> Path | None:
    settings = get_settings()
    path_str = settings.gdrive_service_account_path or settings.gdrive_api_key
    if not path_str:
        return None
    path = Path(path_str)
    return path if path.is_file() else None


def has_service_account_fallback() -> bool:
    return get_service_account_path() is not None


def service_account_token() -> str | None:
    path = get_service_account_path()
    if not path:
        return None

    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except ImportError:
        logger.error(
            "google-auth and requests are required for service account fallback. "
            "Run: pip install google-auth requests"
        )
        return None

    credentials = service_account.Credentials.from_service_account_file(
        str(path),
        scopes=GOOGLE_SCOPE_LIST,
    )
    credentials.refresh(Request())
    return credentials.token
