from typing import Type

from app.connectors.base import Connector
from app.connectors.gdrive import GDriveConnector
from app.connectors.linear import LinearConnector
from app.connectors.notion import NotionConnector
from app.connectors.slack import SlackConnector

CONNECTORS: dict[str, Type[Connector]] = {
    "notion": NotionConnector,
    "linear": LinearConnector,
    "gdrive": GDriveConnector,
    "slack": SlackConnector,
}

SUPPORTED_PROVIDERS = list(CONNECTORS.keys())


def get_connector(provider: str) -> Connector:
    cls = CONNECTORS.get(provider)
    if not cls:
        raise KeyError(f"Unknown provider: {provider}")
    return cls()
