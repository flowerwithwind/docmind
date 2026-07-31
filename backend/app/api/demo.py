"""演示 API（M5/FR-09）：样例信息 / 一键加载 / 幂等与失败重试。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import DEMO_KINDS
from app.models import DemoInfo
from app.seed import DEMO_QUESTIONS, DEMO_SAMPLES
from app.seed_docs import demo_filename, make_demo_docx
from app.services import settings as settings_svc
from app.services.retrieval import INDEX
from app.services.tasks import schedule_demo_load
from app.storage import db
from app.storage import files as file_store

router = APIRouter(prefix="/api/demo", tags=["demo"])

DEMO_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _sample_items() -> list[dict[str, Any]]:
    """样例列表，附带加载状态（同名文档已解析即为已加载）。"""
    out: list[dict[str, Any]] = []
    for s in DEMO_SAMPLES:
        doc = db.get_document_by_original_name(demo_filename(s["kind"]))
        out.append({
            **dict(s),
            "loaded": bool(doc and doc["status"] == "parsed"),
            "doc_id": doc["id"] if doc else None,
        })
    return out


@router.get("")
def demo_info() -> DemoInfo:
    return DemoInfo(
        samples=_sample_items(),
        questions=DEMO_QUESTIONS,
        capabilities=settings_svc.get_capabilities(),
    )


@router.get("/samples")
def demo_samples() -> list[dict[str, Any]]:
    return _sample_items()


def _delete_document_row(row) -> None:
    """删除文档及其文件与索引（演示失败重试时的清理）。"""
    for c in db.list_chunks(row["id"]):
        if c["image_path"]:
            file_store.remove_image(c["image_path"])
    file_store.remove_document_files(row["filename"])
    db.delete_document(row["id"])
    INDEX.drop(row["id"])


@router.post("/load/{kind}", status_code=202)
def load_demo_sample(kind: str) -> dict[str, Any]:
    """一键加载内置样例：生成 docx → 建文档 → 后台解析。

    幂等：同名样例已解析时直接返回既有文档；失败/中断的旧记录自动清理后重试。
    """
    if kind not in DEMO_KINDS:
        raise HTTPException(status_code=404, detail="演示样例不存在")
    filename = demo_filename(kind)
    existing = db.get_document_by_original_name(filename)
    if existing is not None and existing["status"] == "parsed":
        return {"doc_id": existing["id"], "task_id": None, "already_loaded": True}
    if existing is not None and existing["status"] == "parsing":
        raise HTTPException(status_code=409, detail="该样例正在加载，请稍候")
    if existing is not None:
        # failed / uploaded：清理旧记录后重新加载
        _delete_document_row(existing)
    content = make_demo_docx(kind)
    stored = file_store.save_bytes(".docx", content)
    doc_id = db.create_document(
        name=filename,
        filename=stored,
        original_name=filename,
        ext=".docx",
        mime=DEMO_MIME,
        size_bytes=len(content),
        created_at=db.now_iso(),
    )
    task_id = schedule_demo_load(kind, doc_id)
    task = db.get_task(task_id)
    return {"doc_id": doc_id, "task_id": task_id, "task": dict(task), "already_loaded": False}
