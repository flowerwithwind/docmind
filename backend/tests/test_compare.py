"""M5 对比服务与 API 测试（FR-08）。"""
from __future__ import annotations

import json
import time

from app.seed_docs import CONTRACT_V2_PARAGRAPHS
from app.storage import db
from tests.conftest import upload_and_wait
from tests.fixtures.documents import make_docx_bytes
from tests.helpers import schema_id, start_extract, upload_contract


def _wait_task(client, task_id: int, timeout: float = 25.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get(f"/api/tasks/{task_id}").json()
        if task["status"] in ("succeeded", "failed"):
            return task
        time.sleep(0.05)
    raise AssertionError(f"任务超时：task_id={task_id}")


def _upload_contract_v2(client) -> dict:
    content = make_docx_bytes(CONTRACT_V2_PARAGRAPHS)
    return upload_and_wait(client, "购销合同对比版.docx", content)["document"]


def _prepare_pair(client) -> tuple[dict, dict, int]:
    doc_a = upload_contract(client)
    doc_b = _upload_contract_v2(client)
    schema = schema_id(client, "contract")
    for doc in (doc_a, doc_b):
        task = start_extract(client, doc["id"], schema)
        assert task["status"] == "succeeded", task
    return doc_a, doc_b, schema


def _run_compare(client, doc_a: dict, doc_b: dict, schema: int) -> dict:
    r = client.post(
        "/api/compare",
        json={"doc_a_id": doc_a["id"], "doc_b_id": doc_b["id"], "schema_id": schema},
    )
    assert r.status_code == 202, r.text
    task = _wait_task(client, r.json()["task_id"])
    assert task["status"] == "succeeded", task
    return json.loads(task["result_json"])


def _field_map(row: dict) -> dict:
    return {d["key"]: d for d in row["field_diff"]}


def test_compare_flow_detects_field_changes(client):
    """两版合同对比：金额 delta_pct、交付/违约金/有效期/签订日期 changed，其余 same。"""
    doc_a, doc_b, schema = _prepare_pair(client)
    result = _run_compare(client, doc_a, doc_b, schema)
    r = client.get(f"/api/compares/{result['compare_id']}")
    assert r.status_code == 200
    row = r.json()
    assert row["doc_a_name"] == "购销合同.docx"
    assert row["doc_b_name"] == "购销合同对比版.docx"
    fields = _field_map(row)
    assert fields["contract_name"]["status"] == "same"
    assert fields["party_a"]["status"] == "same"
    assert fields["party_b"]["status"] == "same"
    assert fields["currency"]["status"] == "same"
    assert fields["sign_date"]["status"] == "changed"
    assert fields["contract_amount"]["status"] == "changed"
    assert fields["contract_amount"]["delta_pct"] == 8.3
    assert fields["delivery_term"]["status"] == "changed"
    assert fields["penalty_clause"]["status"] == "changed"
    assert fields["valid_period"]["status"] == "changed"
    # 微调章节相似度应 >= 0.6
    assert row["section_diff"], "章节差异不应为空"
    assert all(s["similarity"] >= 0.6 for s in row["section_diff"])
    assert row["summary"]


def test_compare_requires_extraction(client):
    doc_a = upload_contract(client)
    doc_b = _upload_contract_v2(client)
    schema = schema_id(client, "contract")
    r = client.post(
        "/api/compare",
        json={"doc_a_id": doc_a["id"], "doc_b_id": doc_b["id"], "schema_id": schema},
    )
    assert r.status_code == 409
    assert "抽取" in r.json()["detail"]


def test_compare_same_document_422(client):
    doc_a = upload_contract(client)
    schema = schema_id(client, "contract")
    start_extract(client, doc_a["id"], schema)
    r = client.post(
        "/api/compare",
        json={"doc_a_id": doc_a["id"], "doc_b_id": doc_a["id"], "schema_id": schema},
    )
    assert r.status_code == 422


def test_compare_missing_doc_or_schema_404(client):
    r = client.post(
        "/api/compare",
        json={"doc_a_id": 999, "doc_b_id": 998, "schema_id": 1},
    )
    assert r.status_code == 404
    doc_a = upload_contract(client)
    doc_b = _upload_contract_v2(client)
    r = client.post(
        "/api/compare",
        json={"doc_a_id": doc_a["id"], "doc_b_id": doc_b["id"], "schema_id": 99999},
    )
    assert r.status_code == 404


def test_compare_list_and_filter(client):
    doc_a, doc_b, schema = _prepare_pair(client)
    _run_compare(client, doc_a, doc_b, schema)
    rows = client.get("/api/compares").json()
    assert len(rows) == 1
    assert rows[0]["field_diff"]
    rows = client.get(f"/api/compares?doc_id={doc_a['id']}").json()
    assert len(rows) == 1
    rows = client.get("/api/compares?doc_id=12345").json()
    assert rows == []


def test_compare_export_md_html(client):
    doc_a, doc_b, schema = _prepare_pair(client)
    result = _run_compare(client, doc_a, doc_b, schema)
    compare_id = result["compare_id"]

    md = client.get(f"/api/compares/{compare_id}/export?fmt=md")
    assert md.status_code == 200
    assert md.headers["content-type"].startswith("text/markdown")
    body = md.text
    assert "文档对比报告" in body
    assert "## 字段差异" in body
    assert "## 章节差异" in body
    assert "合同金额（元）" in body
    assert "changed" in body
    assert "+8.3%" in body

    html_resp = client.get(f"/api/compares/{compare_id}/export?fmt=html")
    assert html_resp.status_code == 200
    assert html_resp.headers["content-type"].startswith("text/html")
    assert "<table>" in html_resp.text
    assert "文档对比报告" in html_resp.text

    bad = client.get(f"/api/compares/{compare_id}/export?fmt=pdf")
    assert bad.status_code == 422
    missing = client.get("/api/compares/99999/export?fmt=md")
    assert missing.status_code == 404


def test_compare_section_diff_changed_added(client):
    """大改章节 <0.6，新增章节 added，未改章节 same。"""
    # 第一条正文需 >=80 字符，否则会被短块合并策略并入第二条，无法形成独立章节
    first_section = [
        (1, "产品购销合同"),
        (2, "第一条 当事人"),
        (None, "合同名称：产品购销合同"),
        (None, "甲方：华信科技有限公司"),
        (None, "乙方：远景供应链有限公司"),
        (None, "签订日期：2026年3月15日"),
        (None, "合同金额：人民币壹佰贰拾万元整，币种为人民币。"),
        (None, "双方本着平等自愿、诚实信用的原则，经友好协商一致，就甲方向乙方销售产品事宜达成如下协议，双方承诺共同遵守本合同全部条款约定。"),
    ]
    second_a = [
        (2, "第二条 付款与交付"),
        (None, "付款方式：预付30%，验收合格后70%。"),
        (None, "交付期限：合同签订后30日内交货。"),
        (None, "违约金条款：逾期每日按合同金额的0.5%支付违约金。"),
        (None, "争议解决：双方争议提交甲方所在地人民法院诉讼解决。"),
        (None, "有效期限：本合同自签订之日起一年。"),
    ]
    second_b = [
        (2, "第二条 付款与交付"),
        (None, "付款方式：货到验收后30日内以银行承兑汇票一次性付清全部货款。"),
        (None, "交付期限：自收到预付款之日起180日内分批交付完毕。"),
        (None, "违约责任：任何一方违约，守约方有权解除合同并索赔全部直接损失。"),
        (None, "争议解决：提交中国国际经济贸易仲裁委员会仲裁。"),
    ]
    third = [
        (2, "第三条 质量保证"),
        (None, "甲方对所售产品提供自验收之日起二十四个月的免费质保服务。"),
    ]
    doc_a = upload_and_wait(
        client, "原合同.docx", make_docx_bytes(first_section + second_a)
    )["document"]
    doc_b = upload_and_wait(
        client, "重改合同.docx", make_docx_bytes(first_section + second_b + third)
    )["document"]
    schema = schema_id(client, "contract")
    for doc in (doc_a, doc_b):
        task = start_extract(client, doc["id"], schema)
        assert task["status"] == "succeeded", task
    result = _run_compare(client, doc_a, doc_b, schema)
    row = client.get(f"/api/compares/{result['compare_id']}").json()
    sections = {s["title"]: s for s in row["section_diff"]}
    assert sections["产品购销合同 > 第一条 当事人"]["status"] == "same"
    s2 = sections["产品购销合同 > 第二条 付款与交付"]
    assert s2["status"] == "changed"
    assert s2["similarity"] < 0.6
    s3 = sections["产品购销合同 > 第三条 质量保证"]
    assert s3["status"] == "added"
    assert s3["similarity"] == 0.0


def test_compare_only_a_only_b_both_missing(client):
    """构造单边有值 / 双边缺失的抽取数据，验证 diff 状态。"""
    doc_a, doc_b, schema = _prepare_pair(client)
    ext_a = client.get(f"/api/documents/{doc_a['id']}/extractions").json()[0]
    ext_b = client.get(f"/api/documents/{doc_b['id']}/extractions").json()[0]
    data_a = db.jloads(db.get_extraction(ext_a["id"])["data_json"], {})
    data_a.pop("contract_amount", None)
    data_a.pop("valid_period", None)
    db.update_extraction(ext_a["id"], data_json=db.jdumps(data_a))
    data_b = db.jloads(db.get_extraction(ext_b["id"])["data_json"], {})
    data_b.pop("valid_period", None)
    db.update_extraction(ext_b["id"], data_json=db.jdumps(data_b))

    result = _run_compare(client, doc_a, doc_b, schema)
    row = client.get(f"/api/compares/{result['compare_id']}").json()
    fields = _field_map(row)
    assert fields["contract_amount"]["status"] == "only_b"
    assert fields["contract_amount"]["delta_pct"] is None
    assert fields["contract_amount"]["value_a"] is None
    assert fields["valid_period"]["status"] == "both_missing"
    assert fields["party_a"]["status"] == "same"
    assert fields["sign_date"]["status"] == "changed"
