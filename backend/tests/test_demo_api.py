"""M5 演示加载与数据管理 API 测试（FR-09/FR-13）。"""
from __future__ import annotations

import time

from app.config import FILES_DIR
from app.storage import db

from tests.helpers import schema_id, start_extract


def _wait_task(client, task_id: int, timeout: float = 25.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get(f"/api/tasks/{task_id}").json()
        if task["status"] in ("succeeded", "failed"):
            return task
        time.sleep(0.05)
    raise AssertionError(f"任务超时：task_id={task_id}")


def _load(client, kind: str) -> dict:
    r = client.post(f"/api/demo/load/{kind}")
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["already_loaded"] is False
    task = _wait_task(client, body["task_id"])
    assert task["status"] == "succeeded", task
    return body


def test_demo_info_and_samples(client):
    info = client.get("/api/demo").json()
    kinds = {s["kind"] for s in info["samples"]}
    assert kinds == {"contract", "contract_v2", "financial"}
    assert info["questions"]
    assert isinstance(info["capabilities"], dict)

    samples = client.get("/api/demo/samples").json()
    assert all(s["loaded"] is False for s in samples)
    assert all(s["doc_id"] is None for s in samples)


def test_load_contract_idempotent(client):
    body = _load(client, "contract")
    doc_id = body["doc_id"]
    doc = client.get(f"/api/documents/{doc_id}").json()["document"]
    assert doc["status"] == "parsed"

    samples = client.get("/api/demo/samples").json()
    s = next(x for x in samples if x["kind"] == "contract")
    assert s["loaded"] is True
    assert s["doc_id"] == doc_id

    # 幂等：再次加载返回既有文档，不新建任务
    r = client.post("/api/demo/load/contract")
    assert r.status_code == 202, r.text
    again = r.json()
    assert again["already_loaded"] is True
    assert again["doc_id"] == doc_id
    assert again["task_id"] is None


def test_load_all_kinds_full_flow(client):
    """空库点三次卡片完成全流程：加载 → 抽取 → 对比 → 问答。"""
    for kind in ("contract", "contract_v2", "financial"):
        _load(client, kind)
    rows, total = db.list_documents(page_size=100)
    assert total == 3
    docs = {r["original_name"] for r in rows}
    assert docs == {"demo-contract.docx", "demo-contract-v2.docx", "demo-financial.docx"}

    # 合同样例抽取
    contract_schema = schema_id(client, "contract")
    contract_doc = next(r for r in rows if r["original_name"] == "demo-contract.docx")
    v2_doc = next(r for r in rows if r["original_name"] == "demo-contract-v2.docx")
    for doc in (contract_doc, v2_doc):
        task = start_extract(client, doc["id"], contract_schema)
        assert task["status"] == "succeeded", task

    # 双文档对比
    r = client.post(
        "/api/compare",
        json={
            "doc_a_id": contract_doc["id"],
            "doc_b_id": v2_doc["id"],
            "schema_id": contract_schema,
        },
    )
    assert r.status_code == 202, r.text
    task = _wait_task(client, r.json()["task_id"])
    assert task["status"] == "succeeded", task

    # 财报抽取
    fin_schema = schema_id(client, "financial")
    fin_doc = next(r for r in rows if r["original_name"] == "demo-financial.docx")
    task = start_extract(client, fin_doc["id"], fin_schema)
    assert task["status"] == "succeeded", task

    # 问答（规则降级）
    q = client.post(
        f"/api/documents/{contract_doc['id']}/chat",
        json={"question": "合同金额是多少？", "stream": False},
    )
    assert q.status_code == 200, q.text
    assert "120" in q.json()["content"] or "壹佰贰拾" in q.json()["content"]


def test_invalid_demo_kind_404(client):
    r = client.post("/api/demo/load/unknown")
    assert r.status_code == 404


def test_retry_after_failure(client):
    body = _load(client, "contract")
    old_id = body["doc_id"]
    db.update_document(old_id, status="failed", parse_error="模拟失败")

    r = client.post("/api/demo/load/contract")
    assert r.status_code == 202, r.text
    again = r.json()
    assert again["already_loaded"] is False
    assert again["doc_id"] != old_id
    task = _wait_task(client, again["task_id"])
    assert task["status"] == "succeeded", task

    doc = client.get(f"/api/documents/{again['doc_id']}").json()["document"]
    assert doc["status"] == "parsed"
    rows, total = db.list_documents(query="demo-contract", page_size=10)
    assert total == 1
    assert rows[0]["id"] == again["doc_id"]


def test_clear_data_requires_confirm_and_keeps_basics(client):
    body = _load(client, "contract")
    doc_id = body["doc_id"]
    client.post(
        f"/api/documents/{doc_id}/chat",
        json={"question": "你好", "stream": False},
    )
    db.set_setting("custom_flag", {"keep": True})

    # 确认词错误 → 400，数据保留
    r = client.delete("/api/data", params={"confirm": "NO"})
    assert r.status_code == 400
    assert db.list_documents(page_size=10)[1] == 1

    # 正确确认 → 业务数据清空（先记录待删文件的存储名）
    doc_row = db.get_document(doc_id)
    assert doc_row is not None
    stored_name = doc_row["filename"]
    r = client.delete("/api/data", params={"confirm": "DELETE"})
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True
    assert db.list_documents(page_size=10)[1] == 0
    assert db.list_compares() == []
    assert db.list_tasks(limit=100) == []
    assert db.list_sessions() == []
    assert db.get_compare(1) is None

    # 被清空文档的存储文件已删除
    assert not (FILES_DIR / stored_name).exists()

    # 内置 Schema 与设置保留
    schemas = client.get("/api/schemas").json()
    assert {s["key"] for s in schemas} >= {"contract", "financial"}
    assert db.get_setting("custom_flag") == {"keep": True}
