from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:admin123!@localhost:5432/stockinsight"
    dart_api_key: str = ""
    naver_client_id: str = ""
    naver_client_secret: str = ""

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # LLM 설정
    llm_provider: str = "azure_openai"  # azure_openai | openai
    llm_endpoint: str = ""  # Azure OpenAI endpoint URL
    llm_api_key: str = ""  # LLM API key
    llm_deployment: str = ""  # Azure OpenAI deployment name
    llm_model: str = ""  # model name (OpenAI용)

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 24
    admin_email: str = ""
    admin_password: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
