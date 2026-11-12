"""Project Hub settings. All values come from the environment (or .env files)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), ".env"),
        extra="ignore",
    )

    DATABASE_URL: str = "sqlite:///./projecthub.db"
    API_KEY: str = "changeme"
    ADMIN_PASSWORD: str = "admin"
    GITHUB_TOKEN: str | None = None
    CORS_ORIGINS: str = "http://localhost:3000"
    ADMIN_TOKEN_DAYS: int = 7
    OPENAI_API_KEY: str | None = None
    # OpenAI-compatible aliases: LLM_API_KEY / LLM_BASE_URL are accepted too,
    # so either naming in .env configures the LLM.
    LLM_API_KEY: str | None = None
    LLM_BASE_URL: str | None = None
    LLM_MODEL: str = "gpt-4o-mini"
    BOT_URL: str | None = None
    BOT_API_KEY: str | None = None

    @property
    def openai_api_key(self) -> str | None:
        return self.OPENAI_API_KEY or self.LLM_API_KEY

    @property
    def openai_chat_url(self) -> str:
        base = (self.LLM_BASE_URL or "https://api.openai.com/v1").rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
