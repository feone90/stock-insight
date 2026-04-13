from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:admin123!@localhost:5432/stockinsight"
    dart_api_key: str = ""
    naver_client_id: str = ""
    naver_client_secret: str = ""

    # LLM 설정
    llm_provider: str = "azure_openai"  # azure_openai | openai
    llm_endpoint: str = ""  # Azure OpenAI endpoint URL
    llm_api_key: str = ""  # LLM API key
    llm_deployment: str = ""  # Azure OpenAI deployment name
    llm_model: str = ""  # model name (OpenAI용)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
