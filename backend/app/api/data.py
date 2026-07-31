"""数据管理 API（M5/FR-13）：清空全部用户数据（需 DELETE 二次确认）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.retrieval import INDEX
from app.storage import db
from app.storage import files as file_store

router = APIRouter(prefix="/api/data", tags=["data"])


@router.delete("")
def clear_data(confirm: str = "") -> dict[str, bool]:
    """清空全部用户业务数据（保留内置 Schema 与模型设置）。"""
    if confirm != "DELETE":
        raise HTTPException(status_code=400, detail="请在确认框输入 DELETE 以执行清空")
    rows, _ = db.list_documents(page_size=1000)
    for row in rows:
        doc_id = row["id"]
        for c in db.list_chunks(doc_id):
            if c["image_path"]:
                file_store.remove_image(c["image_path"])
        file_store.remove_document_files(row["filename"])
        db.delete_document(doc_id)
        INDEX.drop(doc_id)
    db.clear_user_data()
    return {"deleted": True}
