"""Doctor Excel-export endpoint test (in-memory SQLite fixture).

Registers a doctor, seeds a patient, and downloads /doctor/export.xlsx — then
verifies the bytes are a genuine, parseable OpenXML workbook (via stdlib zipfile,
no openpyxl needed) carrying the seeded data.
"""

import io
import zipfile

from fastapi.testclient import TestClient
from sehaty.db import ClinicPatient
from sqlalchemy.orm import Session, sessionmaker

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_doctor(client: TestClient) -> tuple[int, str]:
    reg = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": "export-doc@clinic.ma",
            "password": "export-pw-123",
            "full_name": "Dr Export",
            "slug": "dr-export",
            "license_no": "LIC-EXPORT-1",
            "phone": "+212613007777",
        },
    )
    assert reg.status_code == 201, reg.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "export-doc@clinic.ma", "password": "export-pw-123"},
    )
    return reg.json()["id"], login.json()["access"]


def test_export_xlsx_download(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, token = _register_doctor(client)
    with db() as s:
        s.add(ClinicPatient(doctor_id=doctor_id, full_name="Zineb El Amrani", phone="+2126001"))
        s.commit()

    resp = client.get("/api/v1/doctor/export.xlsx", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == _XLSX_MEDIA
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.headers["content-disposition"].endswith('.xlsx"')

    # It is a real, parseable xlsx (a zip with the OpenXML parts).
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(zf.namelist())
    assert "[Content_Types].xml" in names
    assert "xl/workbook.xml" in names
    assert "xl/worksheets/sheet1.xml" in names

    # Five sheets, and the seeded patient shows up in the Patients sheet.
    workbook = zf.read("xl/workbook.xml").decode()
    for title in (
        "Patients",
        "Appointments",
        "Consultations",
        "Diagnoses",
        "Prescriptions",
        "Prescription Items",
        "Reviews",
        "Billing",
    ):
        assert f'name="{title}"' in workbook
    assert "Zineb El Amrani" in zf.read("xl/worksheets/sheet1.xml").decode()


def test_export_requires_auth(client: TestClient, db: sessionmaker[Session]) -> None:
    assert client.get("/api/v1/doctor/export.xlsx").status_code == 401
