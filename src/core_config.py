"""Application settings — layered, env-driven.

Reads from the process environment (and a local `.env` in dev). Secrets like
`JWT_SECRET` and the `DATABASE_URL` consumed by `sehaty.core` services live
here so the rest of the app imports a single typed `settings` object.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service metadata
    app_name: str = "Sehaty API"

    # Datastore — consumed by sehaty.core services (get_session reads DATABASE_URL).
    database_url: str = "postgresql+psycopg://sehaty:sehaty@localhost:5432/sehaty"

    # Auth
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # CORS — comma-separated origins; "*" allows any (dev default).
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
