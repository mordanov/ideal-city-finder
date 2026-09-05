from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ideal_city"
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    auth_user_1_username: str = ""
    auth_user_1_password: str = ""
    auth_user_2_username: str = ""
    auth_user_2_password: str = ""
    jwt_secret_key: str = "change-me-in-production"
    jwt_expire_minutes: int = 1440

    # External APIs
    openai_api_key: str = ""
    google_maps_api_key: str = ""
    aemet_api_key: str = ""

    # Rent data source: "idealista_index" or "ine"
    rent_data_source: str = "idealista_index"


settings = Settings()
