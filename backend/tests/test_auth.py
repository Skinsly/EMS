from fastapi.testclient import TestClient


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
