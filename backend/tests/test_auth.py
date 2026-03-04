from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import engine
from app.models import User
from app.security import get_password_hash


def test_healthz_and_bootstrap_status(client: TestClient):
    r = client.get("/healthz")
    assert r.status_code == 200

    s = client.get("/api/bootstrap/status")
    assert s.status_code == 200
    assert "initialized" in s.json()


def test_login_requires_bootstrap_or_valid_credentials(client: TestClient):
    r = client.post("/api/auth/login", json={"username": "nope", "password": "nope"})
    assert r.status_code in (401, 403)


def test_bootstrap_init_and_login_success_flow(client: TestClient):
    init_res = client.post(
        "/api/bootstrap/init",
        json={"username": "admin", "password": "Admin1234"},
    )
    assert init_res.status_code == 200
    body = init_res.json()
    assert body.get("access_token")
    assert body.get("token_type") == "bearer"
    assert body.get("must_change_password") is False

    login_res = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "Admin1234"},
    )
    assert login_res.status_code == 200
    login_body = login_res.json()
    assert login_body.get("access_token")
    assert login_body.get("token_type") == "bearer"


def test_bootstrap_init_rejects_weak_password(client: TestClient):
    init_res = client.post(
        "/api/bootstrap/init",
        json={"username": "admin", "password": "12345678"},
    )
    assert init_res.status_code == 400
    assert "至少8位" in init_res.json().get("detail", "")


def test_non_admin_forbidden_for_high_risk_admin_endpoints(client: TestClient):
    init_res = client.post(
        "/api/bootstrap/init",
        json={"username": "admin", "password": "Admin1234"},
    )
    assert init_res.status_code == 200

    with Session(engine) as db:
        db.add(
            User(
                username="operator",
                password_hash=get_password_hash("Operator123"),
                must_change_password=False,
                is_active=True,
            )
        )
        db.commit()

    login_res = client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "Operator123"},
    )
    assert login_res.status_code == 200
    token = login_res.json().get("access_token")
    assert token
    headers = {"Authorization": f"Bearer {token}"}

    export_res = client.get("/api/export/database", headers=headers)
    assert export_res.status_code == 403

    cleanup_res = client.post("/api/admin/attachments/cleanup", headers=headers)
    assert cleanup_res.status_code == 403

    import_res = client.post(
        "/api/bootstrap/import-package",
        files={"file": ("fake.db", b"x", "application/octet-stream")},
        headers=headers,
    )
    assert import_res.status_code == 403
