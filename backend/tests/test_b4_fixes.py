"""B4 P2 修复测试：抽取防重原子化 / 上传全量校验与补偿删除 / UPDATE 字段白名单。"""
from __future__ import annotations

import threading

import pytest

from app.services.extraction import ExtractionError
from app.services.tasks import schedule_extract
from app.storage import db
from tests.helpers import schema_id


def test_schedule_extract_dedup_second_raises(client, seed_doc):
    sid = schema_id(client, "contract")
    first = schedule_extract(seed_doc["id"], sid)
    assert first is not None
    with pytest.raises(ExtractionError) as ei:
        schedule_extract(seed_doc["id"], sid)
    assert ei.value.args[0] == "该文档正在抽取同一 Schema，请稍后重试"


def test_create_extract_task_atomic_concurrent(client, seed_doc):
    """8 线程同时竞争创建同一 doc+schema 的抽取任务，只允许 1 个成功。"""
    sid = schema_id(client, "contract")
    results: list[int | None] = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        results.append(db.create_extract_task_if_absent(seed_doc["id"], sid))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    created = [r for r in results if r is not None]
    assert len(created) == 1


def test_different_schema_not_blocked(client, seed_doc):
    sid_contract = schema_id(client, "contract")
    sid_financial = schema_id(client, "financial")
    first = db.create_extract_task_if_absent(seed_doc["id"], sid_contract)
    assert first is not None
    second = db.create_extract_task_if_absent(seed_doc["id"], sid_financial)
    assert second is not None
    assert second != first


def test_upload_all_or_nothing(client):
    """多文件上传任一类型非法时，全部拒绝且无文档/文件残留。"""
    from tests.fixtures.documents import make_docx_bytes

    good = make_docx_bytes([(1, "标题"), (None, "正文")])
    r = client.post(
        "/api/documents/upload",
        files=[
            ("files", ("a.docx", good)),
            ("files", ("b.exe", b"MZ")),
            ("files", ("c.docx", good)),
        ],
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "不支持的文件类型：b.exe"
    assert client.get("/api/documents").json()["total"] == 0


def test_update_whitelist_rejects_unknown(client, seed_doc):
    with pytest.raises(ValueError):
        db.update_task(1, evil="x")
    with pytest.raises(ValueError):
        db.update_document(seed_doc["id"], sql="DROP TABLE documents")
    with pytest.raises(ValueError):
        db.update_extraction(1, unknown=1)


def test_update_whitelist_allows_known(client, seed_doc):
    task_id = db.create_task("parse", {"doc_id": seed_doc["id"]})
    db.update_task(task_id, progress=50, message="ok")
    assert db.get_task(task_id)["progress"] == 50
    db.update_document(seed_doc["id"], status="parsed")
    assert db.get_document(seed_doc["id"])["status"] == "parsed"


def test_extract_api_rejects_inflight_duplicate_409(client, seed_doc):
    """API 层：已有进行中抽取任务时重复触发返回 409（防双击）。"""
    sid = schema_id(client, "contract")
    assert db.create_extract_task_if_absent(seed_doc["id"], sid) is not None
    r = client.post(
        f"/api/documents/{seed_doc['id']}/extract", json={"schema_id": sid}
    )
    assert r.status_code == 409
    assert "正在抽取" in r.json()["detail"]


def test_extract_allowed_after_task_finished(client, seed_doc):
    """防重只拦截进行中任务；任务结束后可再次发起抽取。"""
    sid = schema_id(client, "contract")
    first = db.create_extract_task_if_absent(seed_doc["id"], sid)
    assert first is not None
    db.update_task(first, status="succeeded", progress=100, finished_at=db.now_iso())
    second = db.create_extract_task_if_absent(seed_doc["id"], sid)
    assert second is not None
    assert second != first


def test_upload_size_failure_no_residue(client, monkeypatch):
    """第 N 个文件超限时整体失败，文档 / 任务 / 文件均无残留。"""
    from app.config import FILES_DIR
    from tests.fixtures.documents import make_docx_bytes

    monkeypatch.setattr("app.storage.files.UPLOAD_MAX_BYTES", 1024 * 1024)
    good = make_docx_bytes([(1, "标题"), (None, "正文")])
    too_big = b"x" * (1024 * 1024 + 100)
    before = set(FILES_DIR.iterdir())
    r = client.post(
        "/api/documents/upload",
        files=[
            ("files", ("a.docx", good)),
            ("files", ("b.docx", too_big)),
        ],
    )
    assert r.status_code == 413
    assert client.get("/api/documents").json()["total"] == 0
    assert db.list_tasks(kind="parse") == []
    assert set(FILES_DIR.iterdir()) - before == set()


def test_upload_type_failure_no_task_or_file_residue(client):
    """类型校验失败同样清理任务与文件，不留任何残留。"""
    from app.config import FILES_DIR
    from tests.fixtures.documents import make_docx_bytes

    good = make_docx_bytes([(1, "标题"), (None, "正文")])
    before = set(FILES_DIR.iterdir())
    r = client.post(
        "/api/documents/upload",
        files=[
            ("files", ("a.docx", good)),
            ("files", ("b.exe", b"MZ")),
            ("files", ("c.docx", good)),
        ],
    )
    assert r.status_code == 422
    assert client.get("/api/documents").json()["total"] == 0
    assert db.list_tasks(kind="parse") == []
    assert set(FILES_DIR.iterdir()) - before == set()


def test_update_whitelist_rejects_whole_call(client, seed_doc):
    """白名单拒绝时整个 UPDATE 不生效，已知字段也不会被部分写入。"""
    task_id = db.create_task("parse", {"doc_id": seed_doc["id"]})
    with pytest.raises(ValueError):
        db.update_task(task_id, progress=50, evil="x")
    assert db.get_task(task_id)["progress"] == 0
    with pytest.raises(ValueError):
        db.update_document(seed_doc["id"], status="parsed", sql="DROP TABLE documents")
    assert db.get_document(seed_doc["id"])["status"] == "parsed"
