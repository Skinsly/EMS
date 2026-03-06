import base64
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import engine
from app.models import Attachment
from app.services.attachments import cleanup_deleted_attachments, utcnow_naive


def test_projects_requires_auth_header(client: TestClient):
    res = client.get("/api/projects")
    assert res.status_code == 401


def test_projects_create_list_and_delete_flow(client: TestClient, auth_token: str, make_headers):
    create_res = client.post(
        "/api/projects",
        json={"name": "测试工程A", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    )
    assert create_res.status_code == 200
    project_id = create_res.json().get("id")
    assert isinstance(project_id, int)

    list_res = client.get("/api/projects", headers=make_headers(auth_token))
    assert list_res.status_code == 200
    ids = [row.get("id") for row in list_res.json()]
    assert project_id in ids

    wrong_delete = client.request(
        "DELETE",
        f"/api/projects/{project_id}",
        json={"password": "wrong", "confirm_text": "我已知晓删除后不可恢复"},
        headers=make_headers(auth_token),
    )
    assert wrong_delete.status_code == 400

    ok_delete = client.request(
        "DELETE",
        f"/api/projects/{project_id}",
        json={"password": "Admin1234", "confirm_text": "我已知晓删除后不可恢复"},
        headers=make_headers(auth_token),
    )
    assert ok_delete.status_code == 200
    assert ok_delete.json().get("ok") is True


def test_materials_are_project_scoped_and_deletable(client: TestClient, auth_token: str, make_headers):
    p1 = client.post(
        "/api/projects",
        json={"name": "材料工程A", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    ).json()["id"]
    p2 = client.post(
        "/api/projects",
        json={"name": "材料工程B", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    ).json()["id"]

    create_mat = client.post(
        "/api/materials",
        json={"name": "钢筋", "spec": "HRB400", "unit": "吨"},
        headers=make_headers(auth_token, p1),
    )
    assert create_mat.status_code == 200
    material_id = create_mat.json().get("id")
    assert isinstance(material_id, int)

    list_p1 = client.get("/api/materials", headers=make_headers(auth_token, p1))
    assert list_p1.status_code == 200
    assert any(row.get("id") == material_id for row in list_p1.json())

    list_p2 = client.get("/api/materials", headers=make_headers(auth_token, p2))
    assert list_p2.status_code == 200
    assert not any(row.get("id") == material_id for row in list_p2.json())

    update_wrong_project = client.put(
        f"/api/materials/{material_id}",
        json={"name": "钢筋-改", "spec": "HRB500", "unit": "吨"},
        headers=make_headers(auth_token, p2),
    )
    assert update_wrong_project.status_code == 403

    delete_res = client.post(
        "/api/materials/delete",
        json={"material_ids": [material_id]},
        headers=make_headers(auth_token, p1),
    )
    assert delete_res.status_code == 200
    assert delete_res.json().get("deleted") == 1

    list_after = client.get("/api/materials", headers=make_headers(auth_token, p1))
    assert list_after.status_code == 200
    assert not any(row.get("id") == material_id for row in list_after.json())


def test_materials_and_inventory_support_paged_response(client: TestClient, auth_token: str, make_headers):
    project_id = client.post(
        "/api/projects",
        json={"name": "分页工程A", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    ).json()["id"]

    for index in range(12):
        create_res = client.post(
            "/api/materials",
            json={"name": f"材料{index}", "spec": f"规格{index}", "unit": "件"},
            headers=make_headers(auth_token, project_id),
        )
        assert create_res.status_code == 200
        material_id = create_res.json()["id"]
        stock_in_res = client.post(
            "/api/stock-in",
            json={"items": [{"material_id": material_id, "qty": 1, "remark": "备料"}]},
            headers=make_headers(auth_token, project_id),
        )
        assert stock_in_res.status_code == 200

    materials_page = client.get(
        "/api/materials",
        params={"page": 2, "page_size": 5},
        headers=make_headers(auth_token, project_id),
    )
    assert materials_page.status_code == 200
    materials_data = materials_page.json()
    assert materials_data.get("page") == 2
    assert materials_data.get("page_size") == 5
    assert materials_data.get("total") == 12
    assert materials_data.get("total_pages") == 3
    assert len(materials_data.get("items") or []) == 5

    inventory_page = client.get(
        "/api/inventory",
        params={"page": 3, "page_size": 5},
        headers=make_headers(auth_token, project_id),
    )
    assert inventory_page.status_code == 200
    inventory_data = inventory_page.json()
    assert inventory_data.get("page") == 3
    assert inventory_data.get("page_size") == 5
    assert inventory_data.get("total") == 12
    assert inventory_data.get("total_pages") == 3
    assert len(inventory_data.get("items") or []) == 2


def test_construction_logs_support_server_paging_and_search(client: TestClient, auth_token: str, make_headers):
    project_id = client.post(
        "/api/projects",
        json={"name": "日志分页工程A", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    ).json()["id"]

    for index in range(12):
        create_res = client.post(
            "/api/construction-logs",
            json={
                "title": f"施工日志-{index}",
                "log_date": f"2026-02-{index + 1:02d}",
                "weather": "晴" if index % 2 == 0 else "雨",
                "content": f"第{index}天施工记录 特殊标记{index}",
            },
            headers=make_headers(auth_token, project_id),
        )
        assert create_res.status_code == 200

    page_res = client.get(
        "/api/construction-logs",
        params={"page": 2, "page_size": 5},
        headers=make_headers(auth_token, project_id),
    )
    assert page_res.status_code == 200
    page_data = page_res.json()
    assert page_data.get("page") == 2
    assert page_data.get("page_size") == 5
    assert page_data.get("total") == 12
    assert page_data.get("total_pages") == 3
    assert len(page_data.get("items") or []) == 5

    search_res = client.get(
        "/api/construction-logs",
        params={"keyword": "特殊标记11", "page": 1, "page_size": 10},
        headers=make_headers(auth_token, project_id),
    )
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data.get("total") == 1
    assert len(search_data.get("items") or []) == 1
    assert search_data["items"][0]["content"] == "第11天施工记录 特殊标记11"


def test_delete_project_cleans_machine_ledger_rows(client: TestClient, auth_token: str, make_headers):
    create_res = client.post(
        "/api/projects",
        json={"name": "机械清理工程A", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    )
    assert create_res.status_code == 200
    project_id = create_res.json()["id"]

    add_machine = client.post(
        "/api/machine-ledger",
        json={"name": "挖机", "spec": "320", "use_date": "2026-02-26", "shift_count": 1, "remark": "首日"},
        headers=make_headers(auth_token, project_id),
    )
    assert add_machine.status_code == 200

    before_delete = client.get("/api/machine-ledger", headers=make_headers(auth_token, project_id))
    assert before_delete.status_code == 200
    assert len(before_delete.json()) == 1

    delete_res = client.request(
        "DELETE",
        f"/api/projects/{project_id}",
        json={"password": "Admin1234", "confirm_text": "我已知晓删除后不可恢复"},
        headers=make_headers(auth_token),
    )
    assert delete_res.status_code == 200
    assert delete_res.json().get("ok") is True

    recreate_res = client.post(
        "/api/projects",
        json={"name": "机械清理工程A", "start_date": "2026-02-27"},
        headers=make_headers(auth_token),
    )
    assert recreate_res.status_code == 200
    assert recreate_res.json()["id"] == project_id

    after_recreate = client.get("/api/machine-ledger", headers=make_headers(auth_token, project_id))
    assert after_recreate.status_code == 200
    assert after_recreate.json() == []


def test_delete_machine_ledger_also_soft_deletes_its_attachments(client: TestClient, auth_token: str, make_headers):
    create_res = client.post(
        "/api/projects",
        json={"name": "机械附件清理工程A", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    )
    assert create_res.status_code == 200
    project_id = create_res.json()["id"]

    machine_res = client.post(
        "/api/machine-ledger",
        json={"name": "吊机", "spec": "50T", "use_date": "2026-02-26", "shift_count": 1, "remark": "测试"},
        headers=make_headers(auth_token, project_id),
    )
    assert machine_res.status_code == 200
    row_id = machine_res.json()["id"]

    png_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+vXQAAAAASUVORK5CYII=")
    upload_res = client.post(
        "/api/attachments/upload",
        params={"order_type": "machine_ledger", "order_id": row_id},
        files={"file": ("machine.png", png_bytes, "image/png")},
        headers=make_headers(auth_token, project_id),
    )
    assert upload_res.status_code == 200
    attachment_id = upload_res.json()["id"]

    listed = client.get(
        "/api/attachments",
        params={"order_type": "machine_ledger", "order_id": row_id},
        headers=make_headers(auth_token, project_id),
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    delete_res = client.post(
        "/api/machine-ledger/delete",
        json={"ids": [row_id]},
        headers=make_headers(auth_token, project_id),
    )
    assert delete_res.status_code == 200
    assert delete_res.json().get("deleted") == 1

    listed_after = client.get(
        "/api/attachments",
        params={"order_type": "machine_ledger", "order_id": row_id},
        headers=make_headers(auth_token, project_id),
    )
    assert listed_after.status_code == 404

    preview_after = client.get(
        f"/api/attachments/{attachment_id}/preview",
        headers=make_headers(auth_token, project_id),
    )
    assert preview_after.status_code == 404


def test_attachment_preview_rejects_path_outside_uploads(client: TestClient, auth_token: str, make_headers):
    create_res = client.post(
        "/api/projects",
        json={"name": "附件路径校验工程A", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    )
    assert create_res.status_code == 200
    project_id = create_res.json()["id"]

    machine_res = client.post(
        "/api/machine-ledger",
        json={"name": "塔吊", "spec": "QTZ", "use_date": "2026-02-26", "shift_count": 1, "remark": "测试"},
        headers=make_headers(auth_token, project_id),
    )
    assert machine_res.status_code == 200
    row_id = machine_res.json()["id"]

    png_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+vXQAAAAASUVORK5CYII=")
    upload_res = client.post(
        "/api/attachments/upload",
        params={"order_type": "machine_ledger", "order_id": row_id},
        files={"file": ("machine.png", png_bytes, "image/png")},
        headers=make_headers(auth_token, project_id),
    )
    assert upload_res.status_code == 200
    attachment_id = int(upload_res.json()["id"])

    outside_path = Path(__file__).resolve()
    with Session(engine) as db:
        row = db.get(Attachment, attachment_id)
        assert row is not None
        row.stored_name = ""
        row.path = str(outside_path)
        db.commit()

    preview_res = client.get(
        f"/api/attachments/{attachment_id}/preview",
        headers=make_headers(auth_token, project_id),
    )
    assert preview_res.status_code == 404


def test_attachment_cleanup_uses_deleted_time_retention(client: TestClient, auth_token: str, make_headers):
    create_res = client.post(
        "/api/projects",
        json={"name": "附件保留期工程A", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    )
    assert create_res.status_code == 200
    project_id = create_res.json()["id"]

    machine_res = client.post(
        "/api/machine-ledger",
        json={"name": "装载机", "spec": "ZL50", "use_date": "2026-02-26", "shift_count": 1, "remark": "测试"},
        headers=make_headers(auth_token, project_id),
    )
    assert machine_res.status_code == 200
    row_id = machine_res.json()["id"]

    png_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+vXQAAAAASUVORK5CYII=")
    upload_old_res = client.post(
        "/api/attachments/upload",
        params={"order_type": "machine_ledger", "order_id": row_id},
        files={"file": ("old.png", png_bytes, "image/png")},
        headers=make_headers(auth_token, project_id),
    )
    assert upload_old_res.status_code == 200
    old_attachment_id = int(upload_old_res.json()["id"])

    upload_new_res = client.post(
        "/api/attachments/upload",
        params={"order_type": "machine_ledger", "order_id": row_id},
        files={"file": ("new.png", png_bytes, "image/png")},
        headers=make_headers(auth_token, project_id),
    )
    assert upload_new_res.status_code == 200
    new_attachment_id = int(upload_new_res.json()["id"])

    delete_old_res = client.delete(f"/api/attachments/{old_attachment_id}", headers=make_headers(auth_token, project_id))
    delete_new_res = client.delete(f"/api/attachments/{new_attachment_id}", headers=make_headers(auth_token, project_id))
    assert delete_old_res.status_code == 200
    assert delete_new_res.status_code == 200

    now = utcnow_naive()
    with Session(engine) as db:
        old_row = db.get(Attachment, old_attachment_id)
        new_row = db.get(Attachment, new_attachment_id)
        assert old_row is not None and new_row is not None
        old_row.created_at = now - timedelta(days=90)
        old_row.deleted_at = now
        new_row.created_at = now
        new_row.deleted_at = now - timedelta(days=40)
        db.commit()

        result = cleanup_deleted_attachments(db, retention_days=30)
        assert result["deleted_rows"] == 1

        remaining_old = db.get(Attachment, old_attachment_id)
        remaining_new = db.get(Attachment, new_attachment_id)
        assert remaining_old is not None
        assert remaining_new is None


def test_machine_ledger_supports_paged_response(client: TestClient, auth_token: str, make_headers):
    project_id = client.post(
        "/api/projects",
        json={"name": "机械分页工程A", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    ).json()["id"]

    for index in range(12):
        create_res = client.post(
            "/api/machine-ledger",
            json={
                "name": f"机械{index}",
                "spec": f"规格{index}",
                "use_date": "2026-02-26",
                "shift_count": 1,
                "remark": f"备注{index}",
            },
            headers=make_headers(auth_token, project_id),
        )
        assert create_res.status_code == 200

    page_res = client.get(
        "/api/machine-ledger",
        params={"page": 2, "page_size": 5},
        headers=make_headers(auth_token, project_id),
    )
    assert page_res.status_code == 200
    data = page_res.json()
    assert data.get("page") == 2
    assert data.get("page_size") == 5
    assert data.get("total") == 12
    assert data.get("total_pages") == 3
    assert len(data.get("items") or []) == 5
