"""文档 API：上传、列表、详情（页流/结构树/分块）、重解析、删除。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from app.config import MAX_FILES_PER_UPLOAD
from app.models import ChunkOut
from app.services.retrieval import INDEX
from app.services.tasks import schedule_parse
from app.storage import db
from app.storage import files as file_store
from app.storage.files import safe_store

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _doc_out(row) -> dict[str, Any]:
    d = dict(row)
    d.pop("pages_json", None)
    d.pop("tree_json", None)
    return d


@router.post("/upload")
def upload_documents(files: list[UploadFile]) -> list[dict[str, Any]]:
    if not files:
        raise HTTPException(status_code=422, detail="未选择文件")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=422, detail=f"单次最多上传 {MAX_FILES_PER_UPLOAD} 个文件"
        )
    # B4：先全量校验，任一文件不合法则整体拒绝，避免部分入库
    for f in files:
        if not file_store.is_allowed(f.filename or ""):
            raise HTTPException(
                status_code=422, detail=f"不支持的文件类型：{f.filename}"
            )
    results: list[dict[str, Any]] = []
    created: list[tuple[int, str]] = []  # (doc_id, stored filename)
    task_ids: list[int] = []
    try:
        for f in files:
            stored, original, size = safe_store(f)
            doc_id = db.create_document(
                name=original,
                filename=stored,
                original_name=original,
                ext=file_store.ext_of(original),
                mime=f.content_type,
                size_bytes=size,
                created_at=db.now_iso(),
            )
            created.append((doc_id, stored))
            task_id = schedule_parse(doc_id)
            task_ids.append(task_id)
            row = db.get_document(doc_id)
            results.append({"document": _doc_out(row), "task_id": task_id})
        return results
    except Exception:
        # B4：补偿删除已入库文档与文件，避免半成功状态
        for doc_id, stored in created:
            try:
                db.delete_document(doc_id)
            except Exception:  # noqa: BLE001,S110 - 补偿删除失败不阻断主异常
                pass
            try:
                file_store.remove_document_files(stored)
            except Exception:  # noqa: BLE001,S110 - 补偿删除失败不阻断主异常
                pass
        if task_ids:
            try:
                db.delete_tasks_by_ids(task_ids)
            except Exception:  # noqa: BLE001,S110 - 补偿删除失败不阻断主异常
                pass
        raise


@router.get("")
def list_documents(
    query: str = "", status: str = "", ext: str = "", page: int = 1, page_size: int = 20
) -> dict[str, Any]:
    rows, total = db.list_documents(
        query=query,
        status=status,
        ext=ext,
        page=max(page, 1),
        page_size=min(max(page_size, 1), 100),
    )
    return {"total": total, "items": [_doc_out(r) for r in rows]}


@router.get("/{doc_id}")
def get_document(doc_id: int) -> dict[str, Any]:
    row = db.get_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")
    chunks = [dict(c) for c in db.list_chunks(doc_id)]
    return {
        "document": _doc_out(row),
        "pages": db.jloads(row["pages_json"], []),
        "tree": db.jloads(row["tree_json"], None),
        "chunks": [ChunkOut(**c).model_dump() for c in chunks],
    }


@router.post("/{doc_id}/reparse")
def reparse_document(doc_id: int) -> dict[str, Any]:
    row = db.get_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")
    task_id = schedule_parse(doc_id)
    return {"task_id": task_id}


@router.delete("/{doc_id}")
def delete_document(doc_id: int) -> dict[str, Any]:
    row = db.get_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")
    chunks = db.list_chunks(doc_id)
    for c in chunks:
        if c["image_path"]:
            file_store.remove_image(c["image_path"])
    file_store.remove_document_files(row["filename"])
    db.delete_document(doc_id)
    INDEX.drop(doc_id)  # drop stale index
    return {"deleted": doc_id}
