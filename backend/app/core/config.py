from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "FireAtlas"
    debug: bool = True
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://fireatlas:fireatlas@localhost:5432/fireatlas"
    firms_api_key: str = ""
    firms_base_url: str = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
    firms_availability_url: str = "https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv"
    firms_backfill_start: str = "2026-05-14"
    firms_backfill_end: str = "2026-11-13"
    firms_collection_enabled: bool = False
    fireatlas_regional_only: bool = False
    firms_area: str = "68,8,97,37"
    firms_retention_months: int = 6
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
