"""Application settings — layered, env-driven.

Reads from the process environment (and a local `.env` in dev). Secrets like
`JWT_SECRET` and the `DATABASE_URL` consumed by `sehaty.core` services live
here so the rest of the app imports a single typed `settings` object.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Front-ends that must always be able to call this API, whatever the env says.
PRODUCTION_ORIGINS = (
    "https://sehaty-admin.vercel.app",
    "https://sehaty-admin-admin.vercel.app",
    "https://sehaty-maroc.vercel.app",
    "https://sehaty-landing.vercel.app",
)


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

    # CORS — comma-separated exact origins; "*" allows any (dev default).
    cors_origins: str = "*"

    # Vercel mints a fresh hostname for every deployment and every branch, so an
    # exact allowlist is always one deploy behind — which is how the admin
    # console ended up unable to call its own API from a URL Vercel had created
    # for it.
    #
    # Scoped to the *team* slug, never a project prefix. Preview hosts look like
    # `<project>-<hash>-<team>.vercel.app`, so matching on the project would let
    # anyone create a Vercel project called `sehaty-admin-anything` and be
    # trusted by an API that sends credentials. A team slug cannot be squatted.
    cors_origin_regex: str = r"^https://[a-z0-9-]+-zmakhkhas-projects\.vercel\.app$"

    @property
    def cors_origin_list(self) -> list[str]:
        configured = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if "*" in configured:
            return configured
        # The production aliases are always allowed. They are exact strings, not
        # patterns, so nothing here can be squatted — and baking them in means a
        # deployment cannot lose its own front-ends to a stale env var on a box
        # nobody has opened in months.
        return sorted(set(configured) | set(PRODUCTION_ORIGINS))

    @property
    def cors_allows_any(self) -> bool:
        return "*" in self.cors_origin_list


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
