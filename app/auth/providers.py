from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from app.config import Settings


class OAuthModule(Protocol):
    def build_authorization_url(self) -> str: ...
    async def exchange_code_for_token(
        self, code: str, *, pkce_verifier: str | None = None
    ) -> dict[str, Any]: ...
    async def store_oauth_token(self, token_response: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class OAuthProviderSpec:
    name: str
    configured: Callable[[Settings], bool]
    env_hint: str
    build_authorization_url: Callable[[], str]
    exchange_code_for_token: Callable[..., Awaitable[dict[str, Any]]]
    store_oauth_token: Callable[[dict[str, Any]], Awaitable[None]]
    success_message: str


def _notion_spec() -> OAuthProviderSpec:
    from app.auth import notion_oauth

    return OAuthProviderSpec(
        name="notion",
        configured=lambda s: s.notion_oauth_configured,
        env_hint="SPOON_NOTION_CONNECTION_CLIENT_ID and SPOON_NOTION_CONNECTION_SECRET_ID",
        build_authorization_url=notion_oauth.build_authorization_url,
        exchange_code_for_token=notion_oauth.exchange_code_for_token,
        store_oauth_token=notion_oauth.store_oauth_token,
        success_message="Notion connected successfully",
    )


def _gdrive_spec() -> OAuthProviderSpec:
    from app.auth import gdrive_oauth

    return OAuthProviderSpec(
        name="gdrive",
        configured=lambda s: s.gdrive_oauth_configured,
        env_hint="SPOON_GDRIVE_CONNECTION_CLIENT_ID and SPOON_GDRIVE_CONNECTION_SECRET_ID",
        build_authorization_url=gdrive_oauth.build_authorization_url,
        exchange_code_for_token=gdrive_oauth.exchange_code_for_token,
        store_oauth_token=gdrive_oauth.store_oauth_token,
        success_message="Google connected successfully (Drive + Gmail)",
    )


def _slack_spec() -> OAuthProviderSpec:
    from app.auth import slack_oauth

    return OAuthProviderSpec(
        name="slack",
        configured=lambda s: s.slack_oauth_configured,
        env_hint="SPOON_SLACK_CLIENT_ID and SPOON_SLACK_CLIENT_SECRET",
        build_authorization_url=slack_oauth.build_authorization_url,
        exchange_code_for_token=slack_oauth.exchange_code_for_token,
        store_oauth_token=slack_oauth.store_oauth_token,
        success_message="Slack connected successfully",
    )


def _outlook_spec() -> OAuthProviderSpec:
    from app.auth import outlook_oauth

    return OAuthProviderSpec(
        name="outlook",
        configured=lambda s: s.outlook_oauth_configured,
        env_hint="SPOON_OUTLOOK_CONNECTION_CLIENT_ID and SPOON_OUTLOOK_CONNECTION_SECRET_ID",
        build_authorization_url=outlook_oauth.build_authorization_url,
        exchange_code_for_token=outlook_oauth.exchange_code_for_token,
        store_oauth_token=outlook_oauth.store_oauth_token,
        success_message="Outlook connected successfully",
    )


OAUTH_PROVIDERS: dict[str, OAuthProviderSpec] = {
    "notion": _notion_spec(),
    "gdrive": _gdrive_spec(),
    "slack": _slack_spec(),
    "outlook": _outlook_spec(),
}
