from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    LOG_FILE: str = Field("reinhardt.log", env="LOG_FILE")
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")

    class Config:
        # Путь к файлу .env
        env_file = "./infrastructure/config/.env"
        env_file_encoding = "utf-8"


# Создаём экземпляр настроек
settings = Settings()
