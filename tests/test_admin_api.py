"""The employee/attendance endpoints must not be reachable without the admin key."""
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.database.session import get_db
from app.main import app
from tests.conftest import TEST_ADMIN_API_KEY

ADMIN_HEADERS = {"X-Admin-API-Key": TEST_ADMIN_API_KEY}


@pytest.fixture
def client(db_session):
    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


PROTECTED_GETS = ["/api/v1/employees", "/api/v1/attendance", "/api/v1/logs"]


@pytest.mark.parametrize("url", PROTECTED_GETS)
def test_reading_employee_and_attendance_data_requires_the_admin_key(client, url):
    assert client.get(url).status_code == 401


def test_registering_an_employee_requires_the_admin_key(client):
    response = client.post(
        "/api/v1/employees",
        json={
            "slack_user_id": "U_NEW",
            "slack_username": "new_user",
            "marsos_email": "new@example.com",
            "marsos_employee_id": "EMP_NEW",
            "marsos_password": "hunter2",
        },
    )
    assert response.status_code == 401


def test_a_wrong_admin_key_is_rejected(client):
    response = client.get("/api/v1/employees", headers={"X-Admin-API-Key": "not-the-key"})
    assert response.status_code == 401


@pytest.mark.parametrize("url", PROTECTED_GETS)
def test_the_admin_key_grants_access(client, url):
    assert client.get(url, headers=ADMIN_HEADERS).status_code == 200


def test_registering_an_employee_stores_the_password_encrypted(client, db_session):
    response = client.post(
        "/api/v1/employees",
        headers=ADMIN_HEADERS,
        json={
            "slack_user_id": "U_NEW",
            "slack_username": "new_user",
            "marsos_email": "new@example.com",
            "marsos_employee_id": "EMP_NEW",
            "marsos_password": "hunter2",
        },
    )
    assert response.status_code == 201
    # The plaintext password must never come back out of the API.
    assert "hunter2" not in response.text
    assert "password" not in response.json()


def test_a_duplicate_slack_id_is_a_conflict(client, employee):
    response = client.post(
        "/api/v1/employees",
        headers=ADMIN_HEADERS,
        json={
            "slack_user_id": employee.slack_user_id,
            "slack_username": "dupe",
            "marsos_email": "dupe@example.com",
            "marsos_employee_id": "EMP_DUPE",
            "marsos_password": "hunter2",
        },
    )
    assert response.status_code == 409


def test_retrying_an_unknown_employee_is_a_404(client):
    response = client.post("/api/v1/attendance/retry?employee_id=9999", headers=ADMIN_HEADERS)
    assert response.status_code == 404


def test_endpoints_are_disabled_rather_than_open_when_no_key_is_configured(client, monkeypatch):
    """Fail closed: an unconfigured ADMIN_API_KEY must not mean 'no auth required'."""
    monkeypatch.setattr(settings, "ADMIN_API_KEY", None)
    assert client.get("/api/v1/employees").status_code == 503
    assert client.get("/api/v1/employees", headers=ADMIN_HEADERS).status_code == 503


def test_health_check_stays_public(client):
    assert client.get("/health").status_code == 200
