"""pytest 全局夹具：临时数据目录 + 清库测试客户端 + 文档上传解析夹具。"""
from __future__ import annotations

import os
import tempfile
import time

os.environ["DOCMIND_DATA_DIR"] = tempfile.mkdtemp(prefix="docmind-test-")
os.environ["DOCMIND_API_KEY"] = ""

import pytest
from app.main import app
from app.seed import ensure_seed_schemas
from app.storage import db
from fastapi.testclient import TestClient

from tests.fixtures.documents import make_docx_bytes


@pytest.fixture()
def client():
    with TestClient(app) as c:
        db.wipe_data()
        ensure_seed_schemas()
        yield c


def upload_and_wait(client, filename: str, content: bytes, timeout: float = 15.0) -> dict:
    """上传文件并轮询解析任务直到结束，返回 {document, task}。"""
    r = client.post("/api/documents/upload", files={"files": (filename, content)})
    assert r.status_code == 200, r.text
    item = r.json()[0]
    doc = item["document"]
    task_id = item["task_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get(f"/api/tasks/{task_id}").json()
        if task["status"] in ("succeeded", "failed"):
            return {"document": doc, "task": task}
        time.sleep(0.05)
    raise AssertionError(f"解析任务超时：{task_id}")


@pytest.fixture()
def seed_doc(client) -> dict:
    """上传一份带标题/正文的 docx 并完成解析。"""
    content = make_docx_bytes([
        (1, "测试合同"),
        (2, "第一条 标的"),
        (None, "甲方出售服务器 10 台，单价 5000 元。"),
        (2, "第二条 付款"),
        (None, "乙方在收货后 30 日内付清全款。"),
    ])
    return upload_and_wait(client, "测试合同.docx", content)["document"]
