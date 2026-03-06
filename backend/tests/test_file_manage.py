from fastapi.testclient import TestClient

from app.services import project_files as project_files_service


def test_file_categories_and_project_files_flow(client: TestClient, auth_token: str, make_headers):
    project_res = client.post(
        "/api/projects",
        json={"name": "文件管理工程A", "start_date": "2026-03-05"},
        headers=make_headers(auth_token),
    )
    assert project_res.status_code == 200
    project_id = project_res.json()["id"]
    headers = make_headers(auth_token, project_id)

    categories_res = client.get("/api/file-categories", headers=headers)
    assert categories_res.status_code == 200
    category_names = [item.get("name") for item in categories_res.json()]
    assert "施工方案" in category_names

    create_category_res = client.post("/api/file-categories", json={"name": "签证资料"}, headers=headers)
    assert create_category_res.status_code == 200
    category_id = create_category_res.json()["id"]

    upload_res = client.post(
        "/api/project-files/upload",
        params={"category_id": category_id, "remark": "测试文件"},
        files={"file": ("方案.pdf", b"%PDF-1.4 test", "application/pdf")},
        headers=headers,
    )
    assert upload_res.status_code == 200
    file_id = upload_res.json()["id"]

    list_res = client.get("/api/project-files", headers=headers)
    assert list_res.status_code == 200
    assert any(item.get("id") == file_id for item in list_res.json())

    rename_res = client.put(f"/api/file-categories/{category_id}", json={"name": "签证资料A"}, headers=headers)
    assert rename_res.status_code == 200
    assert rename_res.json().get("ok") is True

    delete_need_confirm = client.request(
        "DELETE",
        f"/api/file-categories/{category_id}",
        json={"password": "Admin1234", "delete_files_confirmed": False},
        headers=headers,
    )
    assert delete_need_confirm.status_code == 400
    assert "请确认" in delete_need_confirm.json().get("detail", "")

    delete_ok = client.request(
        "DELETE",
        f"/api/file-categories/{category_id}",
        json={"password": "Admin1234", "delete_files_confirmed": True},
        headers=headers,
    )
    assert delete_ok.status_code == 200
    assert delete_ok.json().get("ok") is True

    list_after_delete = client.get("/api/project-files", headers=headers)
    assert list_after_delete.status_code == 200
    assert not any(item.get("id") == file_id for item in list_after_delete.json())


def test_delete_file_category_requires_password(client: TestClient, auth_token: str, make_headers):
    project_res = client.post(
        "/api/projects",
        json={"name": "文件管理工程B", "start_date": "2026-03-05"},
        headers=make_headers(auth_token),
    )
    assert project_res.status_code == 200
    project_id = project_res.json()["id"]
    headers = make_headers(auth_token, project_id)

    create_category_res = client.post("/api/file-categories", json={"name": "临时分类"}, headers=headers)
    assert create_category_res.status_code == 200
    category_id = create_category_res.json()["id"]

    wrong_pwd_res = client.request(
        "DELETE",
        f"/api/file-categories/{category_id}",
        json={"password": "wrong", "delete_files_confirmed": True},
        headers=headers,
    )
    assert wrong_pwd_res.status_code == 400
    assert "密码" in wrong_pwd_res.json().get("detail", "")


def test_delete_project_file_keeps_record_when_disk_delete_fails(client: TestClient, auth_token: str, make_headers, monkeypatch):
    project_res = client.post(
        "/api/projects",
        json={"name": "文件删除失败工程", "start_date": "2026-03-05"},
        headers=make_headers(auth_token),
    )
    assert project_res.status_code == 200
    project_id = project_res.json()["id"]
    headers = make_headers(auth_token, project_id)

    create_category_res = client.post("/api/file-categories", json={"name": "待删分类"}, headers=headers)
    assert create_category_res.status_code == 200
    category_id = create_category_res.json()["id"]

    upload_res = client.post(
        "/api/project-files/upload",
        params={"category_id": category_id, "remark": "测试文件"},
        files={"file": ("资料.pdf", b"%PDF-1.4 delete test", "application/pdf")},
        headers=headers,
    )
    assert upload_res.status_code == 200
    file_id = upload_res.json()["id"]

    monkeypatch.setattr(project_files_service, "safe_remove_uploaded_file", lambda _: False)

    delete_res = client.delete(f"/api/project-files/{file_id}", headers=headers)
    assert delete_res.status_code == 500
    assert "文件删除失败" in delete_res.json().get("detail", "")

    list_res = client.get("/api/project-files", headers=headers)
    assert list_res.status_code == 200
    assert any(item.get("id") == file_id for item in list_res.json())


def test_project_files_and_categories_support_paged_response(client: TestClient, auth_token: str, make_headers):
    project_res = client.post(
        "/api/projects",
        json={"name": "文件分页工程A", "start_date": "2026-03-05"},
        headers=make_headers(auth_token),
    )
    assert project_res.status_code == 200
    project_id = project_res.json()["id"]
    headers = make_headers(auth_token, project_id)

    create_category_res = client.post("/api/file-categories", json={"name": "分页分类"}, headers=headers)
    assert create_category_res.status_code == 200
    category_id = create_category_res.json()["id"]

    for index in range(12):
        upload_res = client.post(
            "/api/project-files/upload",
            params={"category_id": category_id, "remark": f"备注{index}"},
            files={"file": (f"文件{index}.pdf", b"%PDF-1.4 page test", "application/pdf")},
            headers=headers,
        )
        assert upload_res.status_code == 200

    categories_res = client.get("/api/file-categories", headers=headers)
    assert categories_res.status_code == 200
    category_row = next((item for item in categories_res.json() if item.get("id") == category_id), None)
    assert category_row is not None
    assert category_row.get("file_count") == 12

    files_res = client.get(
        "/api/project-files",
        params={"category_id": category_id, "page": 3, "page_size": 5},
        headers=headers,
    )
    assert files_res.status_code == 200
    data = files_res.json()
    assert data.get("page") == 3
    assert data.get("page_size") == 5
    assert data.get("total") == 12
    assert data.get("total_pages") == 3
    assert len(data.get("items") or []) == 2
