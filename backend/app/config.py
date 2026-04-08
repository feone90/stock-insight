from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:admin123!@localhost:5432/stockinsight"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
