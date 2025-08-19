from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "dev"
    database_url: str = "postgresql+psycopg://postgres:postgres@db:5432/invest"
    fred_api_key: str | None = None
    ofr_liquidity_stress_url: str | None = None
    timezone: str = "America/New_York"

    class Config:
        env_file = ".env"
        env_prefix = ""


settings = Settings()


