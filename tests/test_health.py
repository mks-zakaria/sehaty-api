"""Health endpoint smoke test — must pass WITHOUT a live database.

Only hits `/api/health`; the doctors endpoint needs Postgres and is not
exercised here.
"""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_ok() -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
