from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


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
    spell_api_key: Optional[str] = None
    spell_api_url: Optional[str] = None  # Ej: https://api.openai.com/v1
    spell_api_limit: int = 20  # Max llamadas API por ronda
    spell_fuzzy_threshold: int = 75  # 0-100 umbral fuzzy match


settings = Settings()
