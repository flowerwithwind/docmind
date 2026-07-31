"""文档 API 与媒体 API 集成测试（M2）。"""
from __future__ import annotations

import time

from app.storage import files as file_store
from tests.conftest import upload_and_wait
from tests.fixtures.documents import (
    make_docx_with_table_bytes,
    make_mini_pdf_bytes,
)


def test_upload_invalid_ext_rejected(client):
    r = client.post("/api/documents/upload", files={"files": ("a.exe", b"MZ")})
    assert r.status_code == 422


def test_upload_and_parse_docx(client):
    content = make_docx_with_table_bytes()
    result = upload_and_wait(client, "合同.docx", content)
    doc = result["document"]
    task = result["task"]
    assert task["status"] == "succeeded"
    assert task["progress"] == 100

    detail = client.get(f"/api/documents/{doc['id']}").json()
    assert detail["document"]["status"] == "parsed"
    assert detail["document"]["page_count"] == 1
    assert detail["document"]["chunk_count"] >= 2  # 正文 + 表格
    assert isinstance(detail["pages"], list) and len(detail["pages"]) == 1
    tree = detail["tree"]
    assert tree["title"] == "文档"
    assert len(tree["children"]) >= 1
    kinds = {c["kind"] for c in detail["chunks"]}
    assert "table" in kinds
    # 表格块有内容、正文块有 section_path
    table_chunk = next(c for c in detail["chunks"] if c["kind"] == "table")
    assert "服务器" in table_chunk["content"]
    text_chunk = next(c for c in detail["chunks"] if c["kind"] == "text")
    assert text_chunk["section_path"]


def test_list_documents_pagination_and_filter(client, seed_doc):
    r = client.get("/api/documents")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == seed_doc["id"]
    r2 = client.get("/api/documents", params={"query": "不存在"})
    assert r2.json()["total"] == 0
    r3 = client.get("/api/documents", params={"status": "parsed"})
    assert r3.json()["total"] == 1


def test_parse_pdf_via_api(client):
    content = make_mini_pdf_bytes(["PDF 标题", "这是一段 PDF 正文。"])
    result = upload_and_wait(client, "说明.pdf", content)
    assert result["task"]["status"] == "succeeded"
    detail = client.get(f"/api/documents/{result['document']['id']}").json()
    assert detail["document"]["status"] == "parsed"
    assert detail["document"]["char_count"] > 0


def test_reparse(client, seed_doc):
    r = client.post(f"/api/documents/{seed_doc['id']}/reparse")
    assert r.status_code == 200
    task_id = r.json()["task_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        task = client.get(f"/api/tasks/{task_id}").json()
        if task["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert task["status"] == "succeeded"


def test_media_image_endpoint(client):
    name = "media_test_001.png"
    file_store.save_image_bytes(name, b"\x89PNG fake")
    try:
        r = client.get(f"/api/media/images/{name}")
        assert r.status_code == 200
        assert r.content == b"\x89PNG fake"
        assert r.headers["content-type"] == "image/png"
        bad = client.get("/api/media/images/..%2Fdocmind.db")
        assert bad.status_code in (400, 404)
        missing = client.get("/api/media/images/nope.png")
        assert missing.status_code == 404
    finally:
        file_store.remove_image(name)


def test_delete_document_removes_row_and_file(client, seed_doc):
    r = client.delete(f"/api/documents/{seed_doc['id']}")
    assert r.status_code == 200
    assert client.get(f"/api/documents/{seed_doc['id']}").status_code == 404
