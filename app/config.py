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
    app_url: str = "http://localhost:8000"
    container_tag: str = "spoon"
    notion_version: str = "2022-06-28"
    token_store_path: str = ".data/tokens.json"
    max_block_depth: int = 10
    max_content_length: int = 100_000

    @property
    def oauth_configured(self) -> bool:
        return bool(
            self.notion_connection_client_id and self.notion_connection_secret_id
        )

    @property
    def oauth_redirect_uri(self) -> str:
        if self.notion_connection_authorization_url:
            return self.notion_connection_authorization_url
        return f"{self.app_url.rstrip('/')}/api/v1/auth/notion/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
