"""抽取 API 集成测试（M4/FR-06）：规则模式 / LLM mock / 编辑确认 / 重新抽取 / 导出。"""

from __future__ import annotations

import io
import json
import time

import openpyxl

from app.llm.client import LLMError
from app.storage import db
from tests.helpers import (
    latest_extraction,
    schema_id,
    start_extract,
    upload_contract,
)

CONTRACT_LLM_PAYLOAD = {
    "contract_name": {"value": "产品购销合同", "confidence": 0.97},
    "party_a": {"value": "华信科技有限公司", "confidence": 0.95},
    "party_b": {"value": "远景供应链有限公司", "confidence": 0.95},
    "sign_date": {"value": "2026-03-15", "confidence": 0.9},
    "contract_amount": {"value": 1200000, "confidence": 0.98},
    "currency": {"value": "人民币", "confidence": 0.9},
    "payment_method": {"value": "预付款30%，验收合格后70%", "confidence": 0.85},
    "delivery_term": {"value": "合同签订后30日内交货", "confidence": 0.85},
    "penalty_clause": {"value": "逾期每日按合同金额的0.5%支付违约金", "confidence": 0.85},
    "dispute_resolution": {"value": "提交甲方所在地人民法院诉讼解决", "confidence": 0.85},
    "valid_period": {"value": "自签订之日起一年", "confidence": 0.85},
}


def _wait_task(client, task_id: int, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get(f"/api/tasks/{task_id}").json()
        if task["status"] in ("succeeded", "failed"):
            return task
        time.sleep(0.05)
    raise AssertionError(f"任务超时：{task_id}")


# ---------------------------------------------------------------- 规则模式

def test_extract_rule_mode_flow(client):
    doc = upload_contract(client)
    sid = schema_id(client, "contract")
    task = start_extract(client, doc["id"], sid)
    assert task["status"] == "succeeded"
    assert '"source": "rule"' in task["result_json"]

    ext = latest_extraction(client, doc["id"])
    assert ext["source"] == "rule"
    assert ext["status"] == "draft"
    assert ext["schema_name"] == "合同要素"
    assert ext["data"]["contract_name"] == "产品购销合同"
    assert ext["data"]["party_a"] == "华信科技有限公司"
    assert ext["data"]["party_b"] == "远景供应链有限公司"
    assert ext["data"]["sign_date"] == "2026-03-15"
    assert ext["data"]["contract_amount"] == 1200000
    assert ext["data"]["currency"] == "人民币"
    assert "预付款30%" in ext["data"]["payment_method"]
    assert "30日内交货" in ext["data"]["delivery_term"]
    assert "0.5%" in ext["data"]["penalty_clause"]
    assert "人民法院" in ext["data"]["dispute_resolution"]
    assert "一年" in ext["data"]["valid_period"]
    assert len(ext["data"]) == 11
    assert all(v == "extracted" for v in ext["field_status"].values())
    assert ext["confidence"]["contract_amount"] == 0.9
    assert ext["citations"]["contract_amount"][0]["chunk_id"] > 0

    detail = client.get(f"/api/extractions/{ext['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == ext["id"]


def test_extract_errors(client):
    # 文档不存在
    r = client.post("/api/documents/99999/extract", json={"schema_id": 1})
    assert r.status_code == 404
    # 未解析文档
    doc_id = db.create_document(
        name="未解析",
        filename="u.pdf",
        original_name="未解析.pdf",
        ext=".pdf",
        mime="application/pdf",
        size_bytes=10,
        created_at=db.now_iso(),
    )
    r = client.post(f"/api/documents/{doc_id}/extract", json={"schema_id": 1})
    assert r.status_code == 409
    # Schema 不存在
    doc = upload_contract(client)
    r = client.post(f"/api/documents/{doc['id']}/extract", json={"schema_id": 99999})
    assert r.status_code == 404
    # 抽取结果不存在
    assert client.get("/api/extractions/99999").status_code == 404
    assert client.put("/api/extractions/99999", json={"data": {}}).status_code == 404
    assert client.post("/api/extractions/99999/confirm").status_code == 404
    assert client.post("/api/extractions/99999/reextract").status_code == 404


def test_extract_duplicate_task_conflict(client, monkeypatch):
    doc = upload_contract(client)
    sid = schema_id(client, "contract")
    client.put("/api/settings", json={"model": {"api_key": "sk-fake"}})

    def slow_chat(self, messages, json_mode=False):
        time.sleep(0.5)
        return json.dumps(CONTRACT_LLM_PAYLOAD, ensure_ascii=False)

    monkeypatch.setattr("app.llm.client.LLMClient.chat", slow_chat)
    r1 = client.post(f"/api/documents/{doc['id']}/extract", json={"schema_id": sid})
    assert r1.status_code == 202
    # 同文档同 Schema 进行中任务 → 409
    r2 = client.post(f"/api/documents/{doc['id']}/extract", json={"schema_id": sid})
    assert r2.status_code == 409

    task = _wait_task(client, r1.json()["task_id"])
    assert task["status"] == "succeeded"
    # 完成后可再次发起
    r3 = client.post(f"/api/documents/{doc['id']}/extract", json={"schema_id": sid})
    assert r3.status_code == 202
    _wait_task(client, r3.json()["task_id"])


# ---------------------------------------------------------------- LLM 模式

def test_extract_llm_mode_with_mock(client, monkeypatch):
    doc = upload_contract(client)
    sid = schema_id(client, "contract")
    client.put("/api/settings", json={"model": {"api_key": "sk-fake"}})

    calls = {"n": 0}

    def fake_chat(self, messages, json_mode=False):
        calls["n"] += 1
        return json.dumps(CONTRACT_LLM_PAYLOAD, ensure_ascii=False)

    monkeypatch.setattr("app.llm.client.LLMClient.chat", fake_chat)
    task = start_extract(client, doc["id"], sid)
    assert task["status"] == "succeeded"
    ext = latest_extraction(client, doc["id"])
    assert ext["source"] == "llm"
    assert ext["data"]["contract_amount"] == 1200000
    assert ext["data"]["sign_date"] == "2026-03-15"
    assert ext["confidence"]["contract_amount"] == 0.98
    assert ext["field_status"]["contract_amount"] == "extracted"
    assert calls["n"] == 2  # 11 个字段分 2 批
    assert ext["citations"]["contract_amount"]  # 检索命中引用


def test_extract_llm_invalid_json_marks_invalid(client, monkeypatch):
    doc = upload_contract(client)
    sid = schema_id(client, "contract")
    client.put("/api/settings", json={"model": {"api_key": "sk-fake"}})

    def bad_chat(self, messages, json_mode=False):
        return "抱歉，我无法抽取。"

    monkeypatch.setattr("app.llm.client.LLMClient.chat", bad_chat)
    task = start_extract(client, doc["id"], sid)
    assert task["status"] == "succeeded"
    ext = latest_extraction(client, doc["id"])
    assert ext["source"] == "llm"
    assert all(v == "invalid" for v in ext["field_status"].values())
    assert all(v is None for v in ext["data"].values())
    assert ext["confidence"]["contract_name"] == 0.3


def test_extract_llm_all_fail_falls_back_to_rule(client, monkeypatch):
    doc = upload_contract(client)
    sid = schema_id(client, "contract")
    client.put("/api/settings", json={"model": {"api_key": "sk-fake"}})

    def boom(self, messages, json_mode=False):
        raise LLMError("网络错误")

    monkeypatch.setattr("app.llm.client.LLMClient.chat", boom)
    task = start_extract(client, doc["id"], sid)
    assert task["status"] == "succeeded"
    ext = latest_extraction(client, doc["id"])
    assert ext["source"] == "rule"
    assert ext["data"]["contract_amount"] == 1200000
    assert ext["data"]["party_a"] == "华信科技有限公司"


# ---------------------------------------------------------------- 编辑 / 确认 / 重新抽取

def test_extract_edit_validation(client):
    doc = upload_contract(client)
    sid = schema_id(client, "contract")
    start_extract(client, doc["id"], sid)
    ext = latest_extraction(client, doc["id"])
    eid = ext["id"]

    # 类型错误 422
    r = client.put(f"/api/extractions/{eid}", json={"data": {"contract_amount": "abc"}})
    assert r.status_code == 422
    # 未知字段 422
    r = client.put(f"/api/extractions/{eid}", json={"data": {"unknown_field": 1}})
    assert r.status_code == 422
    # 合法编辑：字段状态 edited、置信度清空
    r = client.put(f"/api/extractions/{eid}", json={"data": {"contract_amount": 1300000}})
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["contract_amount"] == 1300000
    assert body["field_status"]["contract_amount"] == "edited"
    assert "contract_amount" not in body["confidence"]
    # 日期字段可继续编辑并归一化
    r = client.put(f"/api/extractions/{eid}", json={"data": {"sign_date": "2026年4月1日"}})
    assert r.status_code == 200
    assert r.json()["data"]["sign_date"] == "2026-04-01"


def test_extract_confirm_generates_samples(client):
    doc = upload_contract(client)
    sid = schema_id(client, "contract")
    start_extract(client, doc["id"], sid)
    ext = latest_extraction(client, doc["id"])
    eid = ext["id"]

    client.put(f"/api/extractions/{eid}", json={"data": {"contract_amount": 1300000}})
    r = client.post(f"/api/extractions/{eid}/confirm")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "confirmed"
    assert body["confirmed_at"]

    samples = client.get("/api/samples").json()
    assert samples["total"] == 1
    s = samples["items"][0]
    assert s["field_key"] == "contract_amount"
    assert s["model_value"] == "1200000"
    assert s["human_value"] == "1300000"
    assert s["schema_name"] == "合同要素"
    assert s["doc_name"] == "购销合同.docx"

    # 重复确认 409 / 已确认不可编辑
    assert client.post(f"/api/extractions/{eid}/confirm").status_code == 409
    r = client.put(f"/api/extractions/{eid}", json={"data": {"party_a": "X"}})
    assert r.status_code == 409


def test_extract_confirm_auto_no_samples(client):
    doc = upload_contract(client)
    sid = schema_id(client, "contract")
    start_extract(client, doc["id"], sid)
    ext = latest_extraction(client, doc["id"])
    r = client.post(f"/api/extractions/{ext['id']}/confirm")
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"
    assert client.get("/api/samples").json()["total"] == 0


def test_extract_reextract_after_confirm(client):
    doc = upload_contract(client)
    sid = schema_id(client, "contract")
    start_extract(client, doc["id"], sid)
    old = latest_extraction(client, doc["id"])

    # 草稿不可重新抽取
    assert client.post(f"/api/extractions/{old['id']}/reextract").status_code == 409

    client.post(f"/api/extractions/{old['id']}/confirm")
    r = client.post(f"/api/extractions/{old['id']}/reextract")
    assert r.status_code == 202
    task = _wait_task(client, r.json()["task_id"])
    assert task["status"] == "succeeded"

    exts = client.get(f"/api/documents/{doc['id']}/extractions").json()
    assert len(exts) == 2
    assert exts[0]["id"] != old["id"]
    assert exts[0]["status"] == "draft"
    assert exts[1]["id"] == old["id"]
    assert exts[1]["status"] == "confirmed"


# ---------------------------------------------------------------- 导出

def test_extract_export_json(client):
    doc = upload_contract(client)
    sid = schema_id(client, "contract")
    start_extract(client, doc["id"], sid)
    ext = latest_extraction(client, doc["id"])

    r = client.get(f"/api/extractions/{ext['id']}/export", params={"format": "json"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    payload = json.loads(r.content)
    assert payload["schema_name"] == "合同要素"
    assert payload["data"]["contract_amount"] == 1200000
    assert payload["data"]["sign_date"] == "2026-03-15"
    amount_row = next(x for x in payload["rows"] if x["key"] == "contract_amount")
    assert amount_row["value"] == "1200000"
    assert amount_row["status"] == "extracted"


def test_extract_export_excel_and_markdown(client):
    doc = upload_contract(client)
    sid = schema_id(client, "contract")
    start_extract(client, doc["id"], sid)
    ext = latest_extraction(client, doc["id"])
    eid = ext["id"]

    r = client.get(f"/api/extractions/{eid}/export", params={"format": "excel"})
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb.active
    values = [[cell.value for cell in row] for row in ws.iter_rows()]
    assert values[0] == ["字段", "标签", "值", "置信度", "状态", "依据"]
    assert any(v[1] == "合同金额（元）" and v[2] == "1200000" for v in values)

    r = client.get(f"/api/extractions/{eid}/export", params={"format": "markdown"})
    assert r.status_code == 200
    text = r.content.decode("utf-8")
    assert "| 字段 | 标签 | 值 | 置信度 | 状态 | 依据 |" in text
    assert "合同金额（元）" in text
    assert "1200000" in text
    assert "来源：rule" in text

    # 非法格式 / 不存在
    assert client.get(f"/api/extractions/{eid}/export", params={"format": "pdf"}).status_code == 422
    assert client.get("/api/extractions/99999/export", params={"format": "json"}).status_code == 404