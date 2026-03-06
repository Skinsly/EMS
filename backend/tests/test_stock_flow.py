from fastapi.testclient import TestClient


def test_stock_in_out_updates_inventory_and_checks_insufficient_stock(
    client: TestClient, auth_token: str, make_headers
):
    project_id = client.post(
        "/api/projects",
        json={"name": "库存工程A", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    ).json()["id"]

    material_id = client.post(
        "/api/materials",
        json={"name": "水泥", "spec": "P.O42.5", "unit": "袋"},
        headers=make_headers(auth_token, project_id),
    ).json()["id"]

    stock_in_res = client.post(
        "/api/stock-in",
        json={"items": [{"material_id": material_id, "qty": 5, "remark": "首批入库"}]},
        headers=make_headers(auth_token, project_id),
    )
    assert stock_in_res.status_code == 200
    assert (stock_in_res.json().get("order_no") or "").startswith("IN")

    inv_after_in = client.get("/api/inventory", headers=make_headers(auth_token, project_id))
    assert inv_after_in.status_code == 200
    row_after_in = next((row for row in inv_after_in.json() if row.get("material_id") == material_id), None)
    assert row_after_in is not None
    assert row_after_in.get("qty") == "5.000"

    stock_out_res = client.post(
        "/api/stock-out",
        json={"items": [{"material_id": material_id, "qty": 2, "remark": "正常领用"}]},
        headers=make_headers(auth_token, project_id),
    )
    assert stock_out_res.status_code == 200
    assert (stock_out_res.json().get("order_no") or "").startswith("OUT")

    inv_after_out = client.get("/api/inventory", headers=make_headers(auth_token, project_id))
    assert inv_after_out.status_code == 200
    row_after_out = next((row for row in inv_after_out.json() if row.get("material_id") == material_id), None)
    assert row_after_out is not None
    assert row_after_out.get("qty") == "3.000"

    insufficient = client.post(
        "/api/stock-out",
        json={"items": [{"material_id": material_id, "qty": 4, "remark": "超额领用"}]},
        headers=make_headers(auth_token, project_id),
    )
    assert insufficient.status_code == 400
    assert "库存不足" in insufficient.json().get("detail", "")


def test_stock_draft_save_count_commit_flow(client: TestClient, auth_token: str, make_headers):
    project_id = client.post(
        "/api/projects",
        json={"name": "草稿工程A", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    ).json()["id"]

    material_id = client.post(
        "/api/materials",
        json={"name": "砂石", "spec": "中砂", "unit": "方"},
        headers=make_headers(auth_token, project_id),
    ).json()["id"]

    save_in = client.put(
        "/api/stock-drafts/in",
        json=[{"material_id": material_id, "qty": 3, "remark": "草稿入库"}],
        headers=make_headers(auth_token, project_id),
    )
    assert save_in.status_code == 200
    assert save_in.json().get("ok") is True

    pending1 = client.get("/api/stock-drafts/pending/count", headers=make_headers(auth_token, project_id))
    assert pending1.status_code == 200
    assert pending1.json().get("in") == 1
    assert pending1.json().get("total") == 1

    commit_in = client.post("/api/stock-drafts/in/commit", headers=make_headers(auth_token, project_id))
    assert commit_in.status_code == 200
    assert commit_in.json().get("ok") is True
    assert (commit_in.json().get("result", {}).get("order_no") or "").startswith("IN")

    pending2 = client.get("/api/stock-drafts/pending/count", headers=make_headers(auth_token, project_id))
    assert pending2.status_code == 200
    assert pending2.json().get("in") == 0
    assert pending2.json().get("total") == 0

    save_out = client.put(
        "/api/stock-drafts/out",
        json=[{"material_id": material_id, "qty": 2, "remark": "草稿出库"}],
        headers=make_headers(auth_token, project_id),
    )
    assert save_out.status_code == 200

    commit_out = client.post("/api/stock-drafts/out/commit", headers=make_headers(auth_token, project_id))
    assert commit_out.status_code == 200
    assert commit_out.json().get("ok") is True
    assert (commit_out.json().get("result", {}).get("order_no") or "").startswith("OUT")

    inventory = client.get("/api/inventory", headers=make_headers(auth_token, project_id))
    assert inventory.status_code == 200
    row = next((item for item in inventory.json() if item.get("material_id") == material_id), None)
    assert row is not None
    assert row.get("qty") == "1.000"


def test_stock_record_correct_in_creates_reverse_out_and_blocks_repeat(
    client: TestClient, auth_token: str, make_headers
):
    project_id = client.post(
        "/api/projects",
        json={"name": "冲正工程IN", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    ).json()["id"]

    material_id = client.post(
        "/api/materials",
        json={"name": "模板", "spec": "木模", "unit": "张"},
        headers=make_headers(auth_token, project_id),
    ).json()["id"]

    stock_in = client.post(
        "/api/stock-in",
        json={"items": [{"material_id": material_id, "qty": 5, "remark": "原始入库"}]},
        headers=make_headers(auth_token, project_id),
    )
    assert stock_in.status_code == 200
    in_order_no = stock_in.json().get("order_no")
    assert (in_order_no or "").startswith("IN")

    correct_res = client.post(
        "/api/stock-records/correct",
        json={"record_type": "in", "order_no": in_order_no, "reason": "录入错误"},
        headers=make_headers(auth_token, project_id),
    )
    assert correct_res.status_code == 200
    assert correct_res.json().get("ok") is True
    assert (correct_res.json().get("corrected_order_no") or "").startswith("OUT")

    inventory = client.get("/api/inventory", headers=make_headers(auth_token, project_id))
    assert inventory.status_code == 200
    row = next((item for item in inventory.json() if item.get("material_id") == material_id), None)
    assert row is not None
    assert row.get("qty") == "0.000"

    correct_again = client.post(
        "/api/stock-records/correct",
        json={"record_type": "in", "order_no": in_order_no, "reason": "重复冲正"},
        headers=make_headers(auth_token, project_id),
    )
    assert correct_again.status_code == 404


def test_stock_record_correct_out_creates_reverse_in_and_restores_inventory(
    client: TestClient, auth_token: str, make_headers
):
    project_id = client.post(
        "/api/projects",
        json={"name": "冲正工程OUT", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    ).json()["id"]

    material_id = client.post(
        "/api/materials",
        json={"name": "电缆", "spec": "YJV", "unit": "米"},
        headers=make_headers(auth_token, project_id),
    ).json()["id"]

    seed_in = client.post(
        "/api/stock-in",
        json={"items": [{"material_id": material_id, "qty": 8, "remark": "备料"}]},
        headers=make_headers(auth_token, project_id),
    )
    assert seed_in.status_code == 200

    stock_out = client.post(
        "/api/stock-out",
        json={"items": [{"material_id": material_id, "qty": 3, "remark": "发料"}]},
        headers=make_headers(auth_token, project_id),
    )
    assert stock_out.status_code == 200
    out_order_no = stock_out.json().get("order_no")
    assert (out_order_no or "").startswith("OUT")

    correct_res = client.post(
        "/api/stock-records/correct",
        json={"record_type": "out", "order_no": out_order_no, "reason": "单据误录"},
        headers=make_headers(auth_token, project_id),
    )
    assert correct_res.status_code == 200
    assert correct_res.json().get("ok") is True
    assert (correct_res.json().get("corrected_order_no") or "").startswith("IN")

    inventory = client.get("/api/inventory", headers=make_headers(auth_token, project_id))
    assert inventory.status_code == 200
    row = next((item for item in inventory.json() if item.get("material_id") == material_id), None)
    assert row is not None
    assert row.get("qty") == "8.000"


def test_stock_in_blank_idempotency_key_does_not_reuse_previous_result(
    client: TestClient, auth_token: str, make_headers
):
    project_id = client.post(
        "/api/projects",
        json={"name": "幂等空键工程IN", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    ).json()["id"]

    material_id = client.post(
        "/api/materials",
        json={"name": "石灰", "spec": "一级", "unit": "袋"},
        headers=make_headers(auth_token, project_id),
    ).json()["id"]

    first = client.post(
        "/api/stock-in",
        json={"items": [{"material_id": material_id, "qty": 1, "remark": "第一次"}]},
        headers={**make_headers(auth_token, project_id), "X-Idempotency-Key": "abc"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/stock-in",
        json={"items": [{"material_id": material_id, "qty": 1, "remark": "第二次"}]},
        headers={**make_headers(auth_token, project_id), "X-Idempotency-Key": "   "},
    )
    assert second.status_code == 200
    assert first.json().get("order_no") != second.json().get("order_no")


def test_stock_out_blank_idempotency_key_does_not_reuse_previous_result(
    client: TestClient, auth_token: str, make_headers
):
    project_id = client.post(
        "/api/projects",
        json={"name": "幂等空键工程OUT", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    ).json()["id"]

    material_id = client.post(
        "/api/materials",
        json={"name": "砂", "spec": "中砂", "unit": "方"},
        headers=make_headers(auth_token, project_id),
    ).json()["id"]

    seed = client.post(
        "/api/stock-in",
        json={"items": [{"material_id": material_id, "qty": 5, "remark": "备料"}]},
        headers=make_headers(auth_token, project_id),
    )
    assert seed.status_code == 200

    first = client.post(
        "/api/stock-out",
        json={"items": [{"material_id": material_id, "qty": 1, "remark": "第一次"}]},
        headers={**make_headers(auth_token, project_id), "X-Idempotency-Key": "xyz"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/stock-out",
        json={"items": [{"material_id": material_id, "qty": 1, "remark": "第二次"}]},
        headers={**make_headers(auth_token, project_id), "X-Idempotency-Key": " \t "},
    )
    assert second.status_code == 200
    assert first.json().get("order_no") != second.json().get("order_no")


def test_stock_in_rejects_unknown_warehouse(client: TestClient, auth_token: str, make_headers):
    project_id = client.post(
        "/api/projects",
        json={"name": "非法仓库工程IN", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    ).json()["id"]

    material_id = client.post(
        "/api/materials",
        json={"name": "钢筋", "spec": "HRB400", "unit": "吨"},
        headers=make_headers(auth_token, project_id),
    ).json()["id"]

    res = client.post(
        "/api/stock-in",
        json={"warehouse_id": 999999, "items": [{"material_id": material_id, "qty": 1, "remark": "测试"}]},
        headers=make_headers(auth_token, project_id),
    )
    assert res.status_code == 400
    assert "仓库不存在" in res.json().get("detail", "")


def test_stock_out_rejects_unknown_warehouse(client: TestClient, auth_token: str, make_headers):
    project_id = client.post(
        "/api/projects",
        json={"name": "非法仓库工程OUT", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    ).json()["id"]

    material_id = client.post(
        "/api/materials",
        json={"name": "木方", "spec": "50x100", "unit": "根"},
        headers=make_headers(auth_token, project_id),
    ).json()["id"]

    seed = client.post(
        "/api/stock-in",
        json={"items": [{"material_id": material_id, "qty": 3, "remark": "备料"}]},
        headers=make_headers(auth_token, project_id),
    )
    assert seed.status_code == 200

    res = client.post(
        "/api/stock-out",
        json={"warehouse_id": 999999, "items": [{"material_id": material_id, "qty": 1, "remark": "测试"}]},
        headers=make_headers(auth_token, project_id),
    )
    assert res.status_code == 400
    assert "仓库不存在" in res.json().get("detail", "")


def test_stock_draft_commit_rejects_any_invalid_item(client: TestClient, auth_token: str, make_headers):
    project_id = client.post(
        "/api/projects",
        json={"name": "严格草稿工程", "start_date": "2026-02-26"},
        headers=make_headers(auth_token),
    ).json()["id"]

    material_id = client.post(
        "/api/materials",
        json={"name": "石材", "spec": "花岗岩", "unit": "块"},
        headers=make_headers(auth_token, project_id),
    ).json()["id"]

    save_res = client.put(
        "/api/stock-drafts/in",
        json=[
            {"material_id": material_id, "qty": 2, "remark": "有效"},
            {"material_id": 0, "qty": 1, "remark": "无效"},
        ],
        headers=make_headers(auth_token, project_id),
    )
    assert save_res.status_code == 200

    commit_res = client.post("/api/stock-drafts/in/commit", headers=make_headers(auth_token, project_id))
    assert commit_res.status_code == 400
    assert "草稿第 2 条明细无效" in commit_res.json().get("detail", "")

    pending = client.get("/api/stock-drafts/pending/count", headers=make_headers(auth_token, project_id))
    assert pending.status_code == 200
    assert pending.json().get("in") == 2

    inventory = client.get("/api/inventory", headers=make_headers(auth_token, project_id))
    assert inventory.status_code == 200
    row = next((item for item in inventory.json() if item.get("material_id") == material_id), None)
    assert row is None
