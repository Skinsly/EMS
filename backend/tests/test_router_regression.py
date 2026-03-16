import base64

from fastapi.testclient import TestClient


def test_progress_plan_router_crud(client: TestClient, auth_token: str, make_headers):
    project_id = client.post(
        "/api/projects",
        json={"name": "计划路由工程A", "start_date": "2026-03-10"},
        headers=make_headers(auth_token),
    ).json()["id"]
    headers = make_headers(auth_token, project_id)

    create_res = client.post(
        "/api/progress-plans",
        json={
            "task_name": "基础施工",
            "owner": "张三",
            "start_date": "2026-03-10",
            "end_date": "2026-03-12",
            "progress": 10,
            "status": "进行中",
            "predecessor": "",
            "note": "测试",
            "sort_order": 1,
        },
        headers=headers,
    )
    assert create_res.status_code in (200, 401)
    if create_res.status_code == 401:
        return
    item_id = create_res.json()["id"]

    list_res = client.get("/api/progress-plans", headers=headers)
    assert list_res.status_code == 200
    assert any(item["id"] == item_id for item in list_res.json())

    update_res = client.put(
        f"/api/progress-plans/{item_id}",
        json={
            "task_name": "基础施工-更新",
            "owner": "李四",
            "start_date": "2026-03-10",
            "end_date": "2026-03-13",
            "progress": 30,
            "status": "进行中",
            "predecessor": "",
            "note": "已更新",
            "sort_order": 1,
        },
        headers=headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["ok"] is True

    delete_res = client.delete(f"/api/progress-plans/{item_id}", headers=headers)
    assert delete_res.status_code == 200
    assert delete_res.json()["ok"] is True


def test_attachment_router_download_preview_delete_and_cleanup(client: TestClient, auth_token: str, make_headers):
    project_id = client.post(
        "/api/projects",
        json={"name": "附件路由工程A", "start_date": "2026-03-10"},
        headers=make_headers(auth_token),
    ).json()["id"]
    headers = make_headers(auth_token, project_id)

    machine_res = client.post(
        "/api/machine-ledger",
        json={"name": "吊车", "spec": "25T", "use_date": "2026-03-10", "shift_count": 1, "remark": "测试"},
        headers=headers,
    )
    assert machine_res.status_code == 200
    row_id = machine_res.json()["id"]

    png_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+vXQAAAAASUVORK5CYII=")
    upload_res = client.post(
        "/api/attachments/upload",
        params={"order_type": "machine_ledger", "order_id": row_id},
        files={"file": ("machine.png", png_bytes, "image/png")},
        headers=headers,
    )
    assert upload_res.status_code == 200
    attachment_id = upload_res.json()["id"]

    preview_res = client.get(f"/api/attachments/{attachment_id}/preview", headers=headers)
    assert preview_res.status_code == 200

    download_res = client.get(f"/api/attachments/{attachment_id}/download", headers=headers)
    assert download_res.status_code == 200

    site_photos = client.get("/api/site-photos", headers=headers)
    assert site_photos.status_code == 200
    assert any(item["id"] == attachment_id for item in site_photos.json())

    delete_res = client.delete(f"/api/attachments/{attachment_id}", headers=headers)
    assert delete_res.status_code == 200
    assert delete_res.json()["ok"] is True

    cleanup_res = client.post("/api/admin/attachments/cleanup", headers=make_headers(auth_token))
    assert cleanup_res.status_code in (200, 401)


def test_frontend_static_and_database_export_endpoints(client: TestClient, auth_token: str, make_headers):
    db_export = client.get("/api/export/database", headers=make_headers(auth_token))
    assert db_export.status_code == 200

    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["ok"] is True
