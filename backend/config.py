"""Configuration management for the connector agent."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM Configuration
    llm_provider: str = Field(default="gemini")
    llm_api_key: str = Field(default="")
    llm_model: str = Field(default="gemini-2.0-flash")
    llm_base_url: str = Field(default="")

    # Server Configuration
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    debug: bool = Field(default=False)

    # Fetcher Configuration
    fetcher_timeout: int = Field(default=30)
    fetcher_max_pages: int = Field(default=10)

    # LLM Retry Configuration
    llm_max_retries: int = Field(default=3)
    llm_retry_delay: int = Field(default=1)

    class Config:
        env_file = ".env"
        case_sensitive = False


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
