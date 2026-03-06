import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from conftest import TEST_DATA_DIR


def test_import_package_requires_admin_login_when_initialized(client: TestClient, auth_token: str, make_headers):
    no_login = client.post(
        "/api/bootstrap/import-package",
        files={"file": ("demo.db", b"SQLite format 3\x00" + b"x" * 1500, "application/octet-stream")},
    )
    assert no_login.status_code == 401
    assert "登录" in (no_login.json().get("detail") or "")

    logged_in = client.post(
        "/api/bootstrap/import-package",
        files={"file": ("demo.db", b"SQLite format 3\x00" + b"x" * 1500, "application/octet-stream")},
        headers=make_headers(auth_token),
    )
    assert logged_in.status_code == 400
    assert "SQLite" in (logged_in.json().get("detail") or "")


def _build_import_db_bytes(tmp_path: Path, username: str) -> bytes:
    db_path = tmp_path / f"{username}.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT, is_active INTEGER)")
        conn.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE materials (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute(
            "INSERT INTO users (username, password_hash, is_active) VALUES (?, ?, ?)",
            (username, "hash", 1),
        )
        conn.execute("INSERT INTO projects (name) VALUES (?)", ("导入工程",))
        conn.execute("INSERT INTO materials (name) VALUES (?)", ("导入材料",))
        conn.commit()
    return db_path.read_bytes()


def test_import_package_restore_original_db_when_replace_fails(
    client: TestClient, auth_token: str, make_headers, monkeypatch, tmp_path
):
    from app.services import bootstrap_import as bootstrap_import_service

    db_file = TEST_DATA_DIR / "test_app.db"
    assert db_file.exists()

    import_bytes = _build_import_db_bytes(tmp_path, "imported_admin")
    original_replace_file = bootstrap_import_service.replace_file
    replace_calls = {"count": 0}

    def flaky_replace(source, target):
        replace_calls["count"] += 1
        if replace_calls["count"] == 2:
            raise OSError("replace failed")
        return original_replace_file(source, target)

    monkeypatch.setattr(bootstrap_import_service, "replace_file", flaky_replace)

    res = client.post(
        "/api/bootstrap/import-package",
        data={"admin_password": "Admin1234"},
        files={"file": ("demo.db", import_bytes, "application/octet-stream")},
        headers=make_headers(auth_token),
    )
    assert res.status_code == 500
    assert "导入替换失败" in (res.json().get("detail") or "")

    assert db_file.exists()
    with sqlite3.connect(str(db_file)) as conn:
        usernames = {row[0] for row in conn.execute("SELECT username FROM users").fetchall()}
    assert "admin" in usernames
    assert "imported_admin" not in usernames
