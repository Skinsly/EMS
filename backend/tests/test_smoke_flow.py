from fastapi.testclient import TestClient


def test_smoke_login_project_material_stock_and_correct_flow(
    client: TestClient, auth_token: str, make_headers
):
    project_res = client.post(
        "/api/projects",
        json={"name": "冒烟流程工程A", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    )
    assert project_res.status_code == 200
    project_id = project_res.json()["id"]

    material_res = client.post(
        "/api/materials",
        json={"name": "钢板", "spec": "Q235", "unit": "张"},
        headers=make_headers(auth_token, project_id),
    )
    assert material_res.status_code == 200
    material_id = material_res.json()["id"]

    stock_in_res = client.post(
        "/api/stock-in",
        json={"items": [{"material_id": material_id, "qty": 3, "remark": "冒烟入库"}]},
        headers=make_headers(auth_token, project_id),
    )
    assert stock_in_res.status_code == 200
    in_order_no = stock_in_res.json().get("order_no")
    assert (in_order_no or "").startswith("IN")

    records_res = client.get(
        "/api/stock-records",
        params={"record_type": "in", "page": 1, "page_size": 20},
        headers=make_headers(auth_token, project_id),
    )
    assert records_res.status_code == 200
    items = records_res.json().get("items") or []
    assert any((row.get("raw_order_no") or row.get("order_no")) == in_order_no for row in items)

    correct_res = client.post(
        "/api/stock-records/correct",
        json={"record_type": "in", "order_no": in_order_no, "reason": "冒烟冲正"},
        headers=make_headers(auth_token, project_id),
    )
    assert correct_res.status_code == 200
    assert correct_res.json().get("ok") is True
    assert (correct_res.json().get("corrected_order_no") or "").startswith("OUT")

    inventory_res = client.get("/api/inventory", headers=make_headers(auth_token, project_id))
    assert inventory_res.status_code == 200
    row = next((item for item in inventory_res.json() if item.get("material_id") == material_id), None)
    assert row is not None
    assert row.get("qty") == "0.000"
