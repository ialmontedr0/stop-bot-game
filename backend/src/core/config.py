import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    bot_token: str
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/stopbot"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"

    # === Spell correction ===
    spell_mode: str = "local"  # local | ai | hybrid
    spell_api_key: str | None = None
    spell_api_url: str | None = None  # Ej: https://api.openai.com/v1
    spell_api_limit: int = 20  # Max llamadas API por ronda
    spell_fuzzy_threshold: int = 75  # 0-100 umbral fuzzy match
    spell_ai_provider: str = "openai"  # openai | gemini
    spell_ai_model: str | None = None  # auto segun provider si None

    def model_post_init(self, __context) -> None:
        if self.spell_mode in ("ai", "hybrid") and not self.spell_api_key:
            logger.warning(
                "spell_mode=%s pero no hay spell_api_key configurada. "
                "El modo caera a fuzzy matching local.",
                self.spell_mode,
            )


settings = Settings()
