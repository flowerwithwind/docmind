"""修正样本 API 集成测试（M4/FR-07）：列表过滤分页 / JSONL 导出 / 删除清空。"""

from __future__ import annotations

import io
import json

import pandas as pd

from tests.helpers import latest_extraction, schema_id, start_extract, upload_contract


def _make_extraction(client) -> tuple[dict, dict]:
    """上传合同样例并完成一次规则抽取，返回 (document, extraction)。"""
    doc = upload_contract(client)
    sid = schema_id(client, "contract")
    task = start_extract(client, doc["id"], sid)
    assert task["status"] == "succeeded"
    return doc, latest_extraction(client, doc["id"])


def _confirm_with_edits(client, eid: int, edits: dict) -> None:
    """编辑字段并确认，人工值 ≠ 模型值生成修正样本。"""
    assert client.put(f"/api/extractions/{eid}", json={"data": edits}).status_code == 200
    assert client.post(f"/api/extractions/{eid}/confirm").status_code == 200


def test_samples_list_with_names(client):
    _, ext = _make_extraction(client)
    _confirm_with_edits(client, ext["id"], {"contract_amount": 1300000})

    r = client.get("/api/samples")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    s = body["items"][0]
    assert s["field_key"] == "contract_amount"
    assert s["model_value"] == "1200000"
    assert s["human_value"] == "1300000"
    assert s["doc_name"] == "购销合同.docx"
    assert s["schema_name"] == "合同要素"
    assert s["extraction_id"] == ext["id"]
    assert s["citation"]


def test_samples_filter_and_pagination(client):
    _, ext = _make_extraction(client)
    _confirm_with_edits(
        client, ext["id"], {"contract_amount": 1300000, "sign_date": "2026-04-01"}
    )

    # 分页
    r = client.get("/api/samples", params={"page_size": 1, "page": 1}).json()
    assert r["total"] == 2 and len(r["items"]) == 1
    r = client.get("/api/samples", params={"page_size": 1, "page": 2}).json()
    assert r["total"] == 2 and len(r["items"]) == 1
    # 关键词过滤
    assert client.get("/api/samples", params={"query": "contract_amount"}).json()["total"] == 1
    assert client.get("/api/samples", params={"query": "2026-04-01"}).json()["total"] == 1
    assert client.get("/api/samples", params={"query": "不存在的关键词"}).json()["total"] == 0
    # Schema 过滤
    assert client.get("/api/samples", params={"schema_id": ext["schema_id"]}).json()["total"] == 2
    assert client.get("/api/samples", params={"schema_id": 99999}).json()["total"] == 0


def test_samples_export_jsonl(client):
    _, ext = _make_extraction(client)
    _confirm_with_edits(client, ext["id"], {"contract_amount": 1300000})

    r = client.get("/api/samples/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    lines = [ln for ln in r.content.decode("utf-8").splitlines() if ln]
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["field_key"] == "contract_amount"
    assert obj["human_value"] == "1300000"
    assert obj["model_value"] == "1200000"
    assert obj["schema_name"] == "合同要素"
    assert obj["doc_name"] == "购销合同.docx"

    # pandas 可直接读入做微调数据准备
    df = pd.read_json(io.BytesIO(r.content), lines=True)
    assert len(df) == 1
    assert df.iloc[0]["field_key"] == "contract_amount"


def test_samples_export_empty(client):
    r = client.get("/api/samples/export")
    assert r.status_code == 200
    assert r.content == b""


def test_samples_delete_and_clear(client):
    # 删除单条
    _, ext = _make_extraction(client)
    _confirm_with_edits(client, ext["id"], {"contract_amount": 1300000})
    sample = client.get("/api/samples").json()["items"][0]
    sid = sample["id"]

    r = client.delete(f"/api/samples/{sid}")
    assert r.status_code == 200
    assert r.json()["deleted"] == sid
    assert client.delete(f"/api/samples/{sid}").status_code == 404
    assert client.get("/api/samples").json()["total"] == 0

    # 清空全部
    _, ext2 = _make_extraction(client)
    _confirm_with_edits(client, ext2["id"], {"contract_amount": 1300000})
    assert client.get("/api/samples").json()["total"] == 1
    r = client.delete("/api/samples")
    assert r.json()["deleted"] is True
    assert client.get("/api/samples").json()["total"] == 0