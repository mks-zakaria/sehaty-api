"""CORS: every front-end we own can call the API, and nothing else can.

The admin console could not reach its own API from `sehaty-admin-admin.vercel.app`
— a hostname Vercel had created for it. The cause was structural rather than a
missing entry: the allowlist was exact, and Vercel mints a fresh hostname for
every deployment and branch, so the list is always one deploy behind.

The dangerous fix is a project-prefix wildcard. Preview hosts look like
`<project>-<hash>-<team>.vercel.app`, so trusting `sehaty-admin*` would trust any
Vercel project anyone names `sehaty-admin-something` — with credentials attached.
Scoping to the team slug is what makes the pattern safe, and that is what these
tests hold in place.
"""

import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from core_config import PRODUCTION_ORIGINS, Settings


def _app(cors_origins: str = "https://sehaty-maroc.ma") -> TestClient:
    """A minimal app wired the way production is.

    The shared client runs with the permissive `*` dev default, which answers
    every preflight with `*` and would make these assertions pass for the wrong
    reason.
    """
    settings = Settings(cors_origins=cors_origins)
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/probe")
    def probe() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/probe",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )


def test_every_production_front_end_is_allowed() -> None:
    client = _app()
    for origin in PRODUCTION_ORIGINS:
        response = _preflight(client, origin)
        assert response.headers.get("access-control-allow-origin") == origin, origin


def test_the_team_preview_hosts_are_allowed() -> None:
    """Vercel renames the host on every deploy; an exact list cannot keep up."""
    client = _app()
    origin = "https://sehaty-admin-9f2a1c-zmakhkhas-projects.vercel.app"
    assert _preflight(client, origin).headers.get("access-control-allow-origin") == origin

    pattern = re.compile(Settings().cors_origin_regex)

    assert pattern.match("https://sehaty-admin-git-main-zmakhkhas-projects.vercel.app")
    assert pattern.match("https://sehaty-admin-9f2a1c-zmakhkhas-projects.vercel.app")
    assert pattern.match("https://sehaty-maroc-abc123-zmakhkhas-projects.vercel.app")


def test_a_lookalike_project_is_not_trusted() -> None:
    """The reason the pattern keys on the team and not the project name.

    Anyone can create a Vercel project; nobody can create one under another
    team's slug. A project-prefix pattern would hand credentialled access to
    whoever registers `sehaty-admin-evil`.
    """
    pattern = re.compile(Settings().cors_origin_regex)

    assert not pattern.match("https://sehaty-admin-evil.vercel.app")
    assert not pattern.match("https://sehaty-admin.attacker.com")
    assert not pattern.match("https://evil-zmakhkha.vercel.app")
    assert not pattern.match("http://sehaty-admin-x-zmakhkhas-projects.vercel.app")


def test_an_unrelated_origin_is_refused() -> None:
    response = _preflight(_app(), "https://not-ours.example.com")

    assert "access-control-allow-origin" not in response.headers


def test_configured_origins_never_displace_the_defaults() -> None:
    """A stale env var on the droplet must not lock out our own console."""
    allowed = Settings(cors_origins="https://sehaty-maroc.ma").cors_origin_list

    assert "https://sehaty-maroc.ma" in allowed
    for origin in PRODUCTION_ORIGINS:
        assert origin in allowed


def test_the_permissive_dev_default_drops_credentials() -> None:
    """A browser rejects `Allow-Origin: *` on a credentialled request anyway."""
    settings = Settings(cors_origins="*")

    assert settings.cors_allows_any is True
    assert settings.cors_origin_list == ["*"]
