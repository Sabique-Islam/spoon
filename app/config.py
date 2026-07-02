from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="SPOON_", extra="ignore"
    )

    supermemory_api_key: str
    linear_api_key: str | None = None
    notion_api_key: str | None = None
    notion_connection_client_id: str | None = None
    notion_connection_secret_id: str | None = None
    notion_connection_authorization_url: str | None = None
    gdrive_api_key: str | None = None
    gdrive_connection_client_id: str | None = None
    gdrive_connection_secret_id: str | None = None
    gdrive_connection_authorization_url: str | None = None
    slack_app_id: str | None = None
    slack_client_id: str | None = None
    slack_client_secret: str | None = None
    slack_signing_secret: str | None = None
    slack_verification_token: str | None = None
    slack_bot_token: str | None = None
    slack_connection_authorization_url: str | None = None
    app_url: str = "http://localhost:8000"
    container_tag: str = "spoon"
    notion_version: str = "2022-06-28"
    token_store_path: str = ".data/tokens.json"
    max_block_depth: int = 10
    max_content_length: int = 100_000

    @property
    def notion_oauth_configured(self) -> bool:
        return bool(
            self.notion_connection_client_id and self.notion_connection_secret_id
        )

    @property
    def notion_oauth_redirect_uri(self) -> str:
        if self.notion_connection_authorization_url:
            return self.notion_connection_authorization_url
        return f"{self.app_url.rstrip('/')}/api/v1/auth/notion/callback"

    @property
    def gdrive_oauth_configured(self) -> bool:
        return bool(
            self.gdrive_connection_client_id and self.gdrive_connection_secret_id
        )

    @property
    def gdrive_oauth_redirect_uri(self) -> str:
        if self.gdrive_connection_authorization_url:
            return self.gdrive_connection_authorization_url
        return f"{self.app_url.rstrip('/')}/api/v1/auth/gdrive/callback"

    @property
    def slack_oauth_configured(self) -> bool:
        return bool(self.slack_client_id and self.slack_client_secret)

    @property
    def slack_oauth_redirect_uri(self) -> str:
        if self.slack_connection_authorization_url:
            return self.slack_connection_authorization_url
        return f"{self.app_url.rstrip('/')}/api/v1/auth/slack/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
