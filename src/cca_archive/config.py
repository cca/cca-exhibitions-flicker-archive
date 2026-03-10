"""Application configuration via pydantic-settings."""

from pathlib import Path

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

    output_dir: Path = Path("output")
    download_concurrency: int = 5

    @property
    def images_dir(self) -> Path:
        return self.output_dir / "images"

    @property
    def csv_dir(self) -> Path:
        return self.output_dir / "csv"


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
