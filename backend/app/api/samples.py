"""修正样本 API（FR-07）：列表 / JSONL 导出 / 删除单条 / 清空。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.models import SampleOut
from app.storage import db

router = APIRouter(prefix="/api/samples", tags=["samples"])


def _row_to_out(row) -> dict[str, Any]:
    out = SampleOut(
        id=row["id"],
        extraction_id=row["extraction_id"],
        doc_id=row["doc_id"],
        schema_id=row["schema_id"],
        field_key=row["field_key"],
        model_value=row["model_value"],
        human_value=row["human_value"],
        citation=row["citation"] or "",
        created_at=row["created_at"],
    ).model_dump()
    out["doc_name"] = row["doc_name"] or ""
    out["schema_name"] = row["schema_name"] or ""
    return out


@router.get("")
def list_samples(
    query: str = "",
    schema_id: int | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    rows, total = db.list_samples(
        query=query,
        schema_id=schema_id,
        page=max(page, 1),
        page_size=min(max(page_size, 1), 200),
    )
    return {"total": total, "items": [_row_to_out(r) for r in rows]}


@router.get("/export")
def export_samples(query: str = "", schema_id: int | None = None) -> Response:
    """JSONL 导出（每行一个样本对象），可直接被 pandas.read_json(lines=True) 读入。"""
    rows, _ = db.list_samples(query=query, schema_id=schema_id, page=1, page_size=100000)
    lines = []
    for r in rows:
        lines.append(
            json.dumps(
                {
                    "id": r["id"],
                    "extraction_id": r["extraction_id"],
                    "doc_id": r["doc_id"],
                    "schema_id": r["schema_id"],
                    "schema_name": r["schema_name"],
                    "doc_name": r["doc_name"],
                    "field_key": r["field_key"],
                    "model_value": r["model_value"],
                    "human_value": r["human_value"],
                    "citation": r["citation"],
                    "created_at": r["created_at"],
                },
                ensure_ascii=False,
            )
        )
    content = (("\n".join(lines) + "\n") if lines else "").encode("utf-8")
    return Response(
        content=content,
        media_type="application/x-ndjson; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="samples.jsonl"'},
    )


@router.delete("/{sample_id}")
def delete_sample(sample_id: int) -> dict[str, Any]:
    if db.get_sample(sample_id) is None:
        raise HTTPException(status_code=404, detail="样本不存在")
    db.delete_sample(sample_id)
    return {"deleted": sample_id}


@router.delete("")
def clear_samples() -> dict[str, Any]:
    db.clear_samples()
    return {"deleted": True}