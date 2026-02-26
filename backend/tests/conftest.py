import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DATA_DIR = Path(__file__).resolve().parent / ".test-data"
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["DB_PATH"] = "test_app.db"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Base, engine
from app.main import app


@pytest.fixture()
def client() -> TestClient:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestClient(app)


@pytest.fixture()
def auth_token(client: TestClient) -> str:
    init_res = client.post(
        "/api/bootstrap/init",
        json={"username": "admin", "password": "Admin1234"},
    )
    assert init_res.status_code == 200

    login_res = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "Admin1234"},
    )
    assert login_res.status_code == 200
    token = login_res.json().get("access_token")
    assert token
    return token


def headers(token: str, project_id: int | None = None) -> dict:
    result = {"Authorization": f"Bearer {token}"}
    if project_id is not None:
        result["X-Project-Id"] = str(project_id)
    return result


@pytest.fixture()
def make_headers():
    return headers
