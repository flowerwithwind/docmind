"""对比 API（M5/FR-08）：发起对比任务 / 列表 / 详情 / 报告导出（MD/HTML）。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.models import CompareRequest
from app.services.compare import CompareError
from app.services.export import build_compare_export
from app.services.tasks import schedule_compare
from app.storage import db

router = APIRouter(prefix="/api", tags=["compare"])

EXPORT_FORMATS = ("md", "html")


def _compare_out(row) -> dict[str, Any]:
    result = db.jloads(row["result_json"], {})
    doc_a = db.get_document(row["doc_a_id"])
    doc_b = db.get_document(row["doc_b_id"])
    schema = db.get_schema(row["schema_id"])
    return {
        "id": row["id"],
        "doc_a_id": row["doc_a_id"],
        "doc_b_id": row["doc_b_id"],
        "schema_id": row["schema_id"],
        "doc_a_name": doc_a["original_name"] if doc_a else "",
        "doc_b_name": doc_b["original_name"] if doc_b else "",
        "schema_name": schema["name"] if schema else "",
        "created_at": row["created_at"],
        "field_diff": result.get("field_diff", []),
        "section_diff": result.get("section_diff", []),
        "summary": result.get("summary", ""),
        "source": result.get("source", "rule"),
    }


@router.post("/compare", status_code=202)
def start_compare(body: CompareRequest) -> dict[str, Any]:
    if body.doc_a_id == body.doc_b_id:
        raise HTTPException(status_code=422, detail="请选择两份不同的文档")
    for doc_id in (body.doc_a_id, body.doc_b_id):
        doc = db.get_document(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"文档 {doc_id} 不存在")
        if doc["status"] != "parsed":
            raise HTTPException(status_code=409, detail=f"文档 {doc_id} 尚未完成解析")
    if db.get_schema(body.schema_id) is None:
        raise HTTPException(status_code=404, detail="Schema 不存在")
    if (
        db.get_latest_extraction(body.doc_a_id, body.schema_id) is None
        or db.get_latest_extraction(body.doc_b_id, body.schema_id) is None
    ):
        raise HTTPException(status_code=409, detail="参与对比的文档需先完成同 Schema 抽取")
    try:
        task_id = schedule_compare(body.doc_a_id, body.doc_b_id, body.schema_id)
    except CompareError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e
    task = db.get_task(task_id)
    return {"task_id": task_id, "task": dict(task)}


@router.get("/compares")
def list_compares(doc_id: int | None = None) -> list[dict[str, Any]]:
    rows = db.list_compares(doc_id=doc_id)
    return [_compare_out(r) for r in rows]


@router.get("/compares/{compare_id}")
def get_compare(compare_id: int) -> dict[str, Any]:
    row = db.get_compare(compare_id)
    if row is None:
        raise HTTPException(status_code=404, detail="对比结果不存在")
    return _compare_out(row)


@router.get("/compares/{compare_id}/export")
def export_compare(compare_id: int, fmt: str = "md") -> Response:
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(status_code=422, detail=f"支持格式：{'/'.join(EXPORT_FORMATS)}")
    row = db.get_compare(compare_id)
    if row is None:
        raise HTTPException(status_code=404, detail="对比结果不存在")
    content, media, filename = build_compare_export(row, fmt)
    return Response(content=content, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
    })
