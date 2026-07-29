"""The chatbot over the API, with no key configured — today's reality.

The directory works without the chatbot, so an unconfigured deployment has to
degrade rather than fail. And the emergency path has to answer without touching
a model at all: a call that is slow, fails, or hedges is unacceptable in exactly
the case where someone is describing an emergency.
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import User, UserRole
from sqlalchemy.orm import Session, sessionmaker


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin(db: sessionmaker[Session]) -> str:
    with db() as session:
        user = User(
            email="staff-bot@sehaty.test", role=UserRole.ADMIN, is_active=True, password_hash="x"
        )
        session.add(user)
        session.commit()
        return security.create_access_token(int(user.id), UserRole.ADMIN)


def test_status_reports_unconfigured_rather_than_pretending(client: TestClient) -> None:
    """A screen checks this before offering a chat box."""
    assert client.get("/api/v1/chatbot/status").json() == {"available": False}


def test_triage_is_public_and_always_answers(client: TestClient) -> None:
    """A patient asking which doctor they need has no account yet."""
    answer = client.post(
        "/api/v1/chatbot/triage",
        json={"complaint": "j'ai mal aux dents depuis deux jours", "locale": "fr"},
    )

    assert answer.status_code == 200, answer.text
    # No key: falls back to a generalist, which is always a safe answer.
    assert answer.json()["specialty_slug"] == "generalist"
    assert answer.json()["reason"]


def test_an_emergency_never_waits_on_a_model(client: TestClient) -> None:
    answer = client.post(
        "/api/v1/chatbot/triage",
        json={"complaint": "j'ai une douleur à la poitrine", "locale": "fr"},
    )

    body = answer.json()
    assert body["is_emergency"] is True
    assert "150" in body["emergency_numbers"]


def test_translation_says_it_is_not_configured(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """503, not 500: nothing is broken, there is simply no key yet."""
    refused = client.post(
        "/api/v1/chatbot/translate",
        headers=_auth(_admin(db)),
        json={"text": "Cabinet dentaire au Maârif, soins et prothèses.", "locale": "fr"},
    )

    assert refused.status_code == 503, refused.text


def test_translation_is_admin_only(client: TestClient) -> None:
    assert (
        client.post(
            "/api/v1/chatbot/translate", json={"text": "Un texte assez long.", "locale": "fr"}
        ).status_code
        == 401
    )
