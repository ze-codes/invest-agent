from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "dev"
    database_url: str = "postgresql+psycopg://postgres:postgres@db:5432/invest"
    fred_api_key: str | None = None
    ofr_liquidity_stress_url: str | None = None
    timezone: str = "America/New_York"
    # LLM config
    llm_provider: str | None = None  # e.g., "openai", "anthropic", "mock"
    llm_api_key: str | None = None
    llm_model: str | None = None
    openrouter_api_key: str | None = None
    llm_base_url: str | None = None

    class Config:
        env_file = ".env"
        env_prefix = ""


settings = Settings()


