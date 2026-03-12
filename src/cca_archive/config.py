"""Application configuration via pydantic-settings."""

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    flickr_api_key: str
    flickr_api_secret: str
    flickr_user_id: str

    llm_model: str = "anthropic:claude-sonnet-4-20250514"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    skip_llm: bool = False
    output_dir: Path = Path("output")
    download_concurrency: int = 3

    @model_validator(mode="after")
    def _check_llm_api_key(self) -> "Settings":
        if not self.skip_llm and not self.anthropic_api_key and not self.openai_api_key:
            raise ValueError(
                "At least one LLM API key (anthropic_api_key or openai_api_key) "
                "must be provided when skip_llm is not set"
            )
        return self

    @property
    def images_dir(self) -> Path:
        return self.output_dir / "images"

    @property
    def csv_dir(self) -> Path:
        return self.output_dir / "csv"


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
