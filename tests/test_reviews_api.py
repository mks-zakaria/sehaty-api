"""Reviews API integration tests.

The create/reply/flag/moderate/queue surface is non-geo — a review hangs off a
COMPLETED appointment keyed by numeric ids — so it runs on the in-memory SQLite
``client``/``db`` fixtures. The ONE public-by-slug listing
(``GET /api/v1/doctors/{slug}/reviews``) resolves the slug via
``DoctorController.get_by_slug``, which reads the PostGIS ``geopoint`` (ST_X/ST_Y)
and so cannot compile on SQLite; that test takes the ``pg_*`` fixtures and SKIPs
cleanly when no PostGIS is reachable (mirroring ``test_doctors_api.py``), running
for real in CI where a PostGIS service is up.

Flow under test: a patient reviews a COMPLETED appointment (201, PENDING); the
review is invisible publicly until an admin moderates it; the admin queue shows
it; PUBLISH surfaces it publicly and updates the doctor's reputation; a non-admin
moderating is 403; reviewing a non-completed appointment is 409.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.core.controllers.specialties import SpecialtyController
from sehaty.db import ReputationScore, User, UserRole
from sqlalchemy.orm import Session, sessionmaker

# A fixed future date well clear of "today" so the slot always lands in range.
_TARGET_DAY: date = date.today() + timedelta(days=9)
_SLOT_START = datetime(_TARGET_DAY.year, _TARGET_DAY.month, _TARGET_DAY.day, 9, 0, tzinfo=UTC)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login_doctor(client: TestClient, suffix: str, slug: str) -> tuple[int, str]:
    reg = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": f"rev-doc-{suffix}@clinic.ma",
            "password": "rev-pw-123",
            "full_name": f"Dr Review {suffix}",
            "slug": slug,
            "license_no": f"LIC-REV-{suffix}",
            "phone": f"+21261400{suffix:0>4}",
        },
    )
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"rev-doc-{suffix}@clinic.ma", "password": "rev-pw-123"},
    )
    assert login.status_code == 200, login.text
    return doctor_id, login.json()["access"]


def _seed_admin(db: sessionmaker[Session], email: str) -> str:
    with db() as session:
        admin = User(email=email, role=UserRole.ADMIN, is_active=True, password_hash="unused")
        session.add(admin)
        session.commit()
        admin_id = int(admin.id)
    return security.create_access_token(admin_id, UserRole.ADMIN)


def _seed_patient(db: sessionmaker[Session], email: str) -> tuple[int, str]:
    with db() as session:
        patient = User(email=email, role=UserRole.PATIENT, is_active=True, password_hash="unused")
        session.add(patient)
        session.commit()
        patient_id = int(patient.id)
    return patient_id, security.create_access_token(patient_id, UserRole.PATIENT)


def _accredit(client: TestClient, admin_token: str, doctor_id: int) -> None:
    resp = client.post(
        f"/api/v1/admin/professionals/{doctor_id}/accredit",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text


def _completed_appointment(
    client: TestClient,
    doctor_id: int,
    doctor_token: str,
    patient_token: str,
) -> int:
    """Drive the full flow to a COMPLETED appointment and return its id."""
    add = client.post(
        "/api/v1/doctors/me/availability",
        headers=_auth(doctor_token),
        json={
            "weekday": _TARGET_DAY.weekday(),
            "start_time": "09:00",
            "end_time": "10:00",
            "slot_minutes": 30,
        },
    )
    assert add.status_code == 201, add.text

    book = client.post(
        "/api/v1/appointments",
        headers=_auth(patient_token),
        json={"doctor_id": doctor_id, "start_at": _SLOT_START.isoformat(), "reason": "Checkup"},
    )
    assert book.status_code == 201, book.text
    appt_id = int(book.json()["id"])

    confirm = client.patch(
        f"/api/v1/appointments/{appt_id}",
        headers=_auth(doctor_token),
        json={"status": "CONFIRMED"},
    )
    assert confirm.status_code == 200, confirm.text
    complete = client.patch(
        f"/api/v1/appointments/{appt_id}",
        headers=_auth(doctor_token),
        json={"status": "COMPLETED"},
    )
    assert complete.status_code == 200, complete.text
    return appt_id


def test_review_moderation_lifecycle(client: TestClient, db: sessionmaker[Session]) -> None:
    admin_token = _seed_admin(db, "rev-admin1@sehaty.ma")
    doctor_id, doctor_token = _register_and_login_doctor(client, "1", "dr-review-one")
    _accredit(client, admin_token, doctor_id)
    patient_id, patient_token = _seed_patient(db, "rev-patient1@sehaty.ma")
    appt_id = _completed_appointment(client, doctor_id, doctor_token, patient_token)

    # Patient reviews the completed appointment -> 201, PENDING.
    create = client.post(
        "/api/v1/reviews",
        headers=_auth(patient_token),
        json={
            "appointment_id": appt_id,
            "direction": "PATIENT_ON_DOCTOR",
            "stars": 5,
            "comment": "Excellent care",
        },
    )
    assert create.status_code == 201, create.text
    review = create.json()
    review_id = review["id"]
    assert review["status"] == "PENDING"
    assert review["target_id"] == doctor_id
    assert review["author_id"] == patient_id

    # It is NOT yet in the doctor's published reviews (via the controller).
    from sehaty.core.controllers.reviews import ReviewController

    assert ReviewController.list_published_for(doctor_id) == []

    # The admin moderation queue shows it.
    queue = client.get("/api/v1/admin/reviews", headers=_auth(admin_token))
    assert queue.status_code == 200, queue.text
    assert review_id in {r["id"] for r in queue.json()}

    # A non-admin moderating -> 403.
    forbidden = client.post(
        f"/api/v1/admin/reviews/{review_id}/moderate",
        headers=_auth(patient_token),
        json={"action": "PUBLISH"},
    )
    assert forbidden.status_code == 403, forbidden.text

    # The admin publishes it -> 200, PUBLISHED.
    publish = client.post(
        f"/api/v1/admin/reviews/{review_id}/moderate",
        headers=_auth(admin_token),
        json={"action": "PUBLISH"},
    )
    assert publish.status_code == 200, publish.text
    assert publish.json()["status"] == "PUBLISHED"

    # Now it appears in the doctor's published reviews and the queue has cleared it.
    published = ReviewController.list_published_for(doctor_id)
    assert [r.id for r in published] == [review_id]
    queue_after = client.get("/api/v1/admin/reviews", headers=_auth(admin_token))
    assert review_id not in {r["id"] for r in queue_after.json()}

    # The doctor's reputation reflects the published review.
    with db() as session:
        score = session.get(ReputationScore, doctor_id)
        assert score is not None
        assert score.review_count == 1
        assert score.avg_stars == 5.0


def test_review_non_completed_appointment_is_409(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    admin_token = _seed_admin(db, "rev-admin2@sehaty.ma")
    doctor_id, doctor_token = _register_and_login_doctor(client, "2", "dr-review-two")
    _accredit(client, admin_token, doctor_id)
    _patient_id, patient_token = _seed_patient(db, "rev-patient2@sehaty.ma")

    # Book + confirm but do NOT complete.
    add = client.post(
        "/api/v1/doctors/me/availability",
        headers=_auth(doctor_token),
        json={
            "weekday": _TARGET_DAY.weekday(),
            "start_time": "09:00",
            "end_time": "10:00",
            "slot_minutes": 30,
        },
    )
    assert add.status_code == 201, add.text
    book = client.post(
        "/api/v1/appointments",
        headers=_auth(patient_token),
        json={"doctor_id": doctor_id, "start_at": _SLOT_START.isoformat()},
    )
    assert book.status_code == 201, book.text
    appt_id = int(book.json()["id"])

    # Reviewing a non-completed appointment -> 409.
    create = client.post(
        "/api/v1/reviews",
        headers=_auth(patient_token),
        json={"appointment_id": appt_id, "direction": "PATIENT_ON_DOCTOR", "stars": 4},
    )
    assert create.status_code == 409, create.text


def test_public_reviews_by_slug(pg_client: TestClient, pg_db: sessionmaker[Session]) -> None:
    # PostGIS-gated: the public slug listing goes through get_by_slug (ST_X/ST_Y),
    # so it SKIPs locally without a DB and runs for real in CI.
    SpecialtyController.seed_defaults()
    admin_token = _seed_admin(pg_db, "rev-pg-admin@sehaty.ma")
    doctor_id, doctor_token = _register_and_login_doctor(pg_client, "9", "dr-review-pg")

    lat, lng = 33.589886, -7.603869  # Casablanca
    put = pg_client.put(
        "/api/v1/doctors/me/profile",
        headers=_auth(doctor_token),
        json={
            "full_name": "Dr Review PG",
            "city": "Casablanca",
            "lat": lat,
            "lng": lng,
            "specialty_slugs": ["generalist"],
        },
    )
    assert put.status_code == 200, put.text
    slug = put.json()["slug"]
    _accredit(pg_client, admin_token, doctor_id)

    _patient_id, patient_token = _seed_patient(pg_db, "rev-pg-patient@sehaty.ma")
    appt_id = _completed_appointment(pg_client, doctor_id, doctor_token, patient_token)

    create = pg_client.post(
        "/api/v1/reviews",
        headers=_auth(patient_token),
        json={
            "appointment_id": appt_id,
            "direction": "PATIENT_ON_DOCTOR",
            "stars": 5,
            "comment": "Great doctor",
        },
    )
    assert create.status_code == 201, create.text
    review_id = create.json()["id"]

    # Not public while PENDING.
    before = pg_client.get(f"/api/v1/doctors/{slug}/reviews")
    assert before.status_code == 200, before.text
    assert before.json() == []

    moderate = pg_client.post(
        f"/api/v1/admin/reviews/{review_id}/moderate",
        headers=_auth(admin_token),
        json={"action": "PUBLISH"},
    )
    assert moderate.status_code == 200, moderate.text

    # Now public via the slug listing.
    after = pg_client.get(f"/api/v1/doctors/{slug}/reviews")
    assert after.status_code == 200, after.text
    body = after.json()
    assert [r["id"] for r in body] == [review_id]
    assert body[0]["stars"] == 5
    assert body[0]["comment"] == "Great doctor"
    assert body[0]["status"] == "PUBLISHED"
