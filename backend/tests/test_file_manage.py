from fastapi.testclient import TestClient


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
