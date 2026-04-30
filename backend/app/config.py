from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+asyncpg://postgres:admin123!@localhost:5432/stockinsight"
    )
    dart_api_key: str = ""
    naver_client_id: str = ""
    naver_client_secret: str = ""
    newsapi_key: str = ""

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # LLM 설정
    llm_provider: str = "azure_openai"  # azure_openai | openai
    llm_endpoint: str = ""  # Azure OpenAI endpoint URL
    llm_api_key: str = ""  # LLM API key
    llm_deployment: str = ""  # Azure OpenAI deployment name
    llm_model: str = ""  # model name (OpenAI용)

    # Dev mode (skip auth)
    dev_mode: bool = True

    # Data retention
    news_content_retention_days: int = 30

    # Scheduler
    scheduler_enabled: bool = True
    scheduler_morning: str = "08:00"
    scheduler_evening: str = "18:00"
    scheduler_timezone: str = "Asia/Seoul"

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 24
    admin_email: str = ""
    admin_password: str = ""

    # Tavily / analyst
    tavily_api_key: str | None = None
    analyst_research_model: str = "gpt-5-mini"
    analyst_synthesize_model: str = "gpt-5"
    analysis_daily_budget_usd: float = 10.0
    analysis_cooldown_seconds: int = 300

    # Cron strings for scheduler split
    schedule_kr_morning: str = "30 8 * * 1-5"
    schedule_kr_afternoon: str = "0 16 * * 1-5"
    schedule_us_evening: str = "0 7 * * 1-5"
    schedule_us_night: str = "30 22 * * 1-5"

    # SEC EDGAR identifying header (P1.5 / P1.6 v2). Adapter reads via os.environ;
    # declared here so pydantic-settings tolerates the .env line.
    sec_user_agent: str | None = None

    # FRED (Federal Reserve Economic Data) — VIX, US10Y, FedFunds, etc.
    fred_api_key: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
