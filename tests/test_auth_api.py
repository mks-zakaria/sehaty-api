"""Auth API tests over a TestClient with an in-memory SQLite DB.

Covers the doctor credential path (register -> login -> /me), authorization
failures (wrong password, no token), and refresh-token rotation + logout.
"""

from fastapi.testclient import TestClient

_DOCTOR = {
    "email": "doc@clinic.ma",
    "password": "pw-doctor-123",
    "full_name": "Dr Amina",
    "slug": "dr-amina",
    "license_no": "LIC-001",
    "phone": "+212600000001",
}


def _register_and_login(client: TestClient) -> dict:
    reg = client.post("/api/v1/auth/doctor/register", json=_DOCTOR)
    assert reg.status_code == 201, reg.text
    body = reg.json()
    assert body["role"] == "DOCTOR"
    assert body["email"] == _DOCTOR["email"]

    login = client.post(
        "/api/v1/auth/login",
        json={"email": _DOCTOR["email"], "password": _DOCTOR["password"]},
    )
    assert login.status_code == 200, login.text
    tokens = login.json()
    assert set(tokens) == {"access", "refresh", "role"}
    assert tokens["role"] == "DOCTOR"
    return tokens


def test_register_login_and_me(client: TestClient) -> None:
    tokens = _register_and_login(client)
    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access']}"},
    )
    assert resp.status_code == 200, resp.text
    me = resp.json()
    assert me["role"] == "DOCTOR"
    assert me["email"] == _DOCTOR["email"]
    assert me["phone"] == _DOCTOR["phone"]


def test_login_wrong_password_is_rejected(client: TestClient) -> None:
    _register_and_login(client)
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": _DOCTOR["email"], "password": "wrong-pw"},
    )
    assert resp.status_code == 403, resp.text


def test_me_without_token_is_unauthorized(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401, resp.text


def test_me_with_garbage_token_is_unauthorized(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not.a.jwt"},
    )
    assert resp.status_code == 401, resp.text


def test_refresh_rotates_and_invalidates_old(client: TestClient) -> None:
    tokens = _register_and_login(client)
    rotated = client.post("/api/v1/auth/refresh", json={"refresh": tokens["refresh"]})
    assert rotated.status_code == 200, rotated.text
    new_tokens = rotated.json()
    assert new_tokens["refresh"] != tokens["refresh"]

    # The new access token authenticates /me.
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_tokens['access']}"},
    )
    assert me.status_code == 200

    # Replaying the old refresh token after rotation is rejected.
    replay = client.post("/api/v1/auth/refresh", json={"refresh": tokens["refresh"]})
    assert replay.status_code == 403, replay.text


def test_logout_revokes_refresh(client: TestClient) -> None:
    tokens = _register_and_login(client)
    out = client.post("/api/v1/auth/logout", json={"refresh": tokens["refresh"]})
    assert out.status_code == 204, out.text

    # A revoked refresh token can no longer be rotated.
    resp = client.post("/api/v1/auth/refresh", json={"refresh": tokens["refresh"]})
    assert resp.status_code == 403, resp.text
