"""M4 测试辅助：合同/财报样例文档与抽取流程封装。"""
from __future__ import annotations

import time

from tests.conftest import upload_and_wait
from tests.fixtures.documents import make_docx_bytes

CONTRACT_PARAGRAPHS = [
    (1, "产品购销合同"),
    (2, "第一条 当事人"),
    (None, "合同名称：产品购销合同"),
    (None, "甲方：华信科技有限公司"),
    (None, "乙方：远景供应链有限公司"),
    (None, "签订日期：2026年3月15日"),
    (None, "合同金额：人民币壹佰贰拾万元整，币种为人民币。"),
    (2, "第二条 付款与交付"),
    (None, "付款方式：预付款30%，验收合格后70%。"),
    (None, "交付期限：合同签订后30日内交货。"),
    (None, "违约金条款：逾期每日按合同金额的0.5%支付违约金。"),
    (None, "争议解决：双方争议提交甲方所在地人民法院诉讼解决。"),
    (None, "有效期：本合同自签订之日起一年。"),
]

FINANCIAL_PARAGRAPHS = [
    (1, "2025年年度报告"),
    (None, "报告期：2025年年度，公司主营业务：智能硬件研发与销售。"),
    (None, "营业收入85600万元，营业收入同比增长12.5%。"),
    (None, "净利润9800万元，净利润同比增长8.2%。"),
    (None, "毛利率32.1%，资产负债率45.6%，基本每股收益1.25元。"),
]


def upload_contract(client, name: str = "购销合同.docx") -> dict:
    """上传一份完整合同样例并等待解析完成。"""
    content = make_docx_bytes(CONTRACT_PARAGRAPHS)
    return upload_and_wait(client, name, content)["document"]


def upload_financial(client, name: str = "财报摘要.docx") -> dict:
    """上传一份财报指标样例并等待解析完成。"""
    content = make_docx_bytes(FINANCIAL_PARAGRAPHS)
    return upload_and_wait(client, name, content)["document"]


def schema_id(client, key: str) -> int:
    """按 key 查找内置 Schema 的 id。"""
    for s in client.get("/api/schemas").json():
        if s["key"] == key:
            return s["id"]
    raise AssertionError(f"内置 Schema {key} 不存在")


def start_extract(client, doc_id: int, schema_id: int, timeout: float = 20.0) -> dict:
    """发起抽取并轮询任务直到结束，返回任务对象。"""
    r = client.post(f"/api/documents/{doc_id}/extract", json={"schema_id": schema_id})
    assert r.status_code == 202, r.text
    task_id = r.json()["task_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get(f"/api/tasks/{task_id}").json()
        if task["status"] in ("succeeded", "failed"):
            return task
        time.sleep(0.05)
    raise AssertionError(f"抽取任务超时：task_id={task_id}")


def latest_extraction(client, doc_id: int) -> dict:
    """返回文档最新一条抽取结果（列表按 id 倒序）。"""
    exts = client.get(f"/api/documents/{doc_id}/extractions").json()
    assert exts, "该文档还没有抽取结果"
    return exts[0]