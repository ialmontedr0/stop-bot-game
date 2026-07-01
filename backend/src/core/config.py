from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    bot_token: str
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/stopbot"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"


settings = Settings()
