import argparse
import random
import string
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.main import app


def _rand_suffix(length: int = 6) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def _fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def _ok(message: str) -> None:
    print(f"OK: {message}")


def _login(client: TestClient, username: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    if resp.status_code != 200:
        _fail(f"login failed ({resp.status_code}): {resp.text}")
    token_obj = (resp.json() or {}).get("access_token")
    if not isinstance(token_obj, str) or not token_obj:
        _fail("login token is empty")
    token = str(token_obj)
    _ok(f"login ({username})")
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description="EMS backend end-to-end smoke test")
    parser.add_argument("--username", default="", help="existing admin username")
    parser.add_argument("--password", default="", help="existing admin password")
    args = parser.parse_args()

    with TestClient(app) as client:
        health = client.get("/healthz")
        if health.status_code != 200 or not (health.json() or {}).get("ok"):
            _fail(f"healthz unexpected: {health.status_code} {health.text}")
        _ok("healthz")

        status = client.get("/api/bootstrap/status")
        if status.status_code != 200:
            _fail(f"bootstrap status failed: {status.status_code} {status.text}")
        initialized = bool((status.json() or {}).get("initialized"))
        _ok(f"bootstrap initialized={initialized}")

        username = args.username.strip()
        password = args.password.strip()

        if initialized:
            if not username or not password:
                _fail("system already initialized; pass --username and --password")
        else:
            if not username:
                username = f"qa_admin_{_rand_suffix()}"
            if not password:
                password = f"Qa{_rand_suffix()}1234"
            init_resp = client.post("/api/bootstrap/init", json={"username": username, "password": password})
            if init_resp.status_code != 200:
                _fail(f"bootstrap init failed: {init_resp.status_code} {init_resp.text}")
            _ok("bootstrap init")

        token = _login(client, username, password)
        auth = {"Authorization": f"Bearer {token}"}

        suffix = _rand_suffix()
        project_name = f"qa_project_{suffix}"
        material_name = f"cement_{suffix}"

        project_resp = client.post("/api/projects", headers=auth, json={"name": project_name, "start_date": "2026-02-26"})
        if project_resp.status_code != 200:
            _fail(f"create project failed: {project_resp.status_code} {project_resp.text}")
        project_id = (project_resp.json() or {}).get("id")
        if not project_id:
            _fail("create project missing id")
        _ok(f"create project id={project_id}")

        pheaders = {**auth, "X-Project-Id": str(project_id)}

        material_resp = client.post(
            "/api/materials",
            headers=pheaders,
            json={"name": material_name, "spec": "P.O42.5", "unit": "t"},
        )
        if material_resp.status_code != 200:
            _fail(f"create material failed: {material_resp.status_code} {material_resp.text}")
        material_id = (material_resp.json() or {}).get("id")
        if not material_id:
            _fail("create material missing id")
        _ok(f"create material id={material_id}")

        draft_resp = client.put(
            "/api/stock-drafts/in",
            headers=pheaders,
            json=[{"date": "2026-02-26", "material_id": material_id, "qty": "2.5", "remark": "qa"}],
        )
        if draft_resp.status_code != 200:
            _fail(f"save draft failed: {draft_resp.status_code} {draft_resp.text}")
        _ok("save stock-in draft")

        commit_resp = client.post("/api/stock-drafts/in/commit", headers=pheaders)
        if commit_resp.status_code != 200:
            _fail(f"commit draft failed: {commit_resp.status_code} {commit_resp.text}")
        order_no = ((commit_resp.json() or {}).get("result") or {}).get("order_no", "")
        if not order_no:
            _fail("commit draft missing order_no")
        _ok(f"commit stock-in draft order_no={order_no}")

        inventory_resp = client.get("/api/inventory", headers=pheaders)
        if inventory_resp.status_code != 200:
            _fail(f"inventory list failed: {inventory_resp.status_code} {inventory_resp.text}")
        rows = inventory_resp.json() or []
        targets = [row for row in rows if row.get("material_id") == material_id]
        if not targets:
            _fail("inventory missing material after commit")
        qty = str(targets[0].get("qty"))
        if qty not in {"2.5", "2.50", "2.500"}:
            _fail(f"inventory qty unexpected: {qty}")
        _ok(f"inventory qty={qty}")

        records_resp = client.get(
            "/api/stock-records",
            headers=pheaders,
            params={"record_type": "in", "page": 1, "page_size": 20},
        )
        if records_resp.status_code != 200:
            _fail(f"stock records failed: {records_resp.status_code} {records_resp.text}")
        items = ((records_resp.json() or {}).get("items") or [])
        if not any(item.get("order_no") == order_no for item in items):
            _fail("stock records missing committed order")
        _ok("stock records contain order")

        correct_resp = client.post(
            "/api/stock-records/correct",
            headers=pheaders,
            json={"record_type": "in", "order_no": order_no, "reason": "qa-correct"},
        )
        if correct_resp.status_code != 200:
            _fail(f"correct record failed: {correct_resp.status_code} {correct_resp.text}")
        _ok("correct stock record")

        inventory_after_resp = client.get("/api/inventory", headers=pheaders)
        if inventory_after_resp.status_code != 200:
            _fail(f"inventory list after correction failed: {inventory_after_resp.status_code} {inventory_after_resp.text}")
        rows_after = inventory_after_resp.json() or []
        targets_after = [row for row in rows_after if row.get("material_id") == material_id]
        if not targets_after:
            _fail("inventory missing material after correction")
        qty_after = str(targets_after[0].get("qty"))
        if qty_after not in {"0", "0.0", "0.00", "0.000"}:
            _fail(f"inventory qty after correction unexpected: {qty_after}")
        _ok(f"inventory qty after correction={qty_after}")

    print("E2E_SMOKE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
