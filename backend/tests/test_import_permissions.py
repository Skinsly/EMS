from fastapi.testclient import TestClient


def test_import_package_requires_admin_password_when_initialized(client: TestClient, auth_token: str, make_headers):
    no_pwd = client.post(
        "/api/bootstrap/import-package",
        files={"file": ("demo.db", b"SQLite format 3\x00" + b"x" * 1500, "application/octet-stream")},
        headers=make_headers(auth_token),
    )
    assert no_pwd.status_code == 400
    assert "密码" in (no_pwd.json().get("detail") or "")
