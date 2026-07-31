"""抽取 API（M4/FR-06）：发起 / 列表 / 详情 / 编辑 / 确认 / 重新抽取 / 导出。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.models import Citation, ExtractRequest, ExtractionEditIn, ExtractionOut, TaskOut
from app.services.export import build_export
from app.services.extraction import ExtractionError
from app.services.tasks import schedule_extract
from app.storage import db
from app.utils.text import normalize_value

documents_router = APIRouter(prefix="/api/documents", tags=["extractions"])
router = APIRouter(prefix="/api/extractions", tags=["extractions"])

EXPORT_FORMATS = ("json", "excel", "markdown")


def _citations(row) -> dict[str, list[Citation]]:
    raw = db.jloads(row["citations_json"], {})
    out: dict[str, list[Citation]] = {}
    for key, value in raw.items():
        if isinstance(value, list):
            out[key] = [Citation(**c) for c in value if isinstance(c, dict)]
    return out


def _row_to_out(row) -> ExtractionOut:
    return ExtractionOut(
        id=row["id"],
        doc_id=row["doc_id"],
        schema_id=row["schema_id"],
        status=row["status"],
        data=db.jloads(row["data_json"], {}),
        confidence=db.jloads(row["confidence_json"], {}),
        field_status=db.jloads(row["field_status_json"], {}),
        citations=_citations(row),
        source=row["source"] or "llm",
        error=row["error"],
        confirmed_at=row["confirmed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _task_out(row) -> TaskOut:
    return TaskOut(
        id=row["id"], kind=row["kind"], status=row["status"], progress=row["progress"],
        message=row["message"] or "", result_json=row["result_json"],
        error=row["error"], created_at=row["created_at"], finished_at=row["finished_at"],
    )


@documents_router.post("/{doc_id}/extract", status_code=202)
def start_extract(doc_id: int, body: ExtractRequest) -> dict[str, Any]:
    doc = db.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc["status"] != "parsed":
        raise HTTPException(status_code=409, detail="文档尚未完成解析，请稍后重试")
    if db.get_schema(body.schema_id) is None:
        raise HTTPException(status_code=404, detail="Schema 不存在")
    try:
        task_id = schedule_extract(doc_id, body.schema_id)
    except ExtractionError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e
    return {"task_id": task_id, "task": _task_out(db.get_task(task_id))}


@documents_router.get("/{doc_id}/extractions")
def list_doc_extractions(doc_id: int) -> list[dict[str, Any]]:
    if db.get_document(doc_id) is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    out: list[dict[str, Any]] = []
    for row in db.list_extractions(doc_id):
        item = _row_to_out(row).model_dump()
        schema = db.get_schema(row["schema_id"])
        item["schema_name"] = schema["name"] if schema else ""
        out.append(item)
    return out


@router.get("/{extraction_id}")
def get_extraction(extraction_id: int) -> ExtractionOut:
    row = db.get_extraction(extraction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="抽取结果不存在")
    return _row_to_out(row)


@router.put("/{extraction_id}")
def save_extraction(extraction_id: int, body: ExtractionEditIn) -> ExtractionOut:
    """保存草稿：人工编辑字段值；编辑后该字段 confidence 置空、status=edited。"""
    row = db.get_extraction(extraction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="抽取结果不存在")
    if row["status"] == "confirmed":
        raise HTTPException(status_code=409, detail="已确认的抽取不可编辑，请重新抽取")
    schema = db.get_schema(row["schema_id"])
    fields = db.jloads(schema["fields_json"], []) if schema else []
    by_key = {f["key"]: f for f in fields}

    data = db.jloads(row["data_json"], {})
    confidence = db.jloads(row["confidence_json"], {})
    field_status = db.jloads(row["field_status_json"], {})
    for key, value in body.data.items():
        field = by_key.get(key)
        if field is None:
            raise HTTPException(status_code=422, detail=f"未知字段：{key}")
        normalized, ok = normalize_value(field, value)
        if not ok:
            raise HTTPException(
                status_code=422,
                detail=f"字段「{field.get('label') or key}」的值不符合 {field.get('type')} 类型",
            )
        data[key] = normalized
        confidence.pop(key, None)
        field_status[key] = "edited"
    db.update_extraction(
        extraction_id,
        data_json=db.jdumps(data),
        confidence_json=db.jdumps(confidence),
        field_status_json=db.jdumps(field_status),
    )
    return _row_to_out(db.get_extraction(extraction_id))


def _value_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


@router.post("/{extraction_id}/confirm")
def confirm_extraction(extraction_id: int) -> ExtractionOut:
    """确认抽取：模型值 ≠ 人工值的已编辑字段生成修正样本；重复确认 409。"""
    row = db.get_extraction(extraction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="抽取结果不存在")
    if row["status"] == "confirmed":
        raise HTTPException(status_code=409, detail="该抽取结果已确认，请勿重复确认")
    if db.get_samples_for_extraction(extraction_id):
        raise HTTPException(status_code=409, detail="该抽取结果已生成修正样本，请勿重复确认")

    data = db.jloads(row["data_json"], {})
    model_json = db.jloads(row["model_json"], data)
    field_status = db.jloads(row["field_status_json"], {})
    citations = db.jloads(row["citations_json"], {})
    now = db.now_iso()

    samples: list[dict[str, Any]] = []
    for key, human_value in data.items():
        if field_status.get(key) != "edited":
            continue
        model_value = model_json.get(key)
        if _value_str(model_value) == _value_str(human_value):
            continue
        snippet = ""
        cites = citations.get(key) or []
        if cites and isinstance(cites[0], dict):
            snippet = str(cites[0].get("snippet") or "")
        samples.append(
            {
                "extraction_id": extraction_id,
                "doc_id": row["doc_id"],
                "schema_id": row["schema_id"],
                "field_key": key,
                "model_value": _value_str(model_value),
                "human_value": _value_str(human_value) or "",
                "citation": snippet[:200],
                "created_at": now,
            }
        )
    if samples:
        db.insert_samples(samples)
    db.update_extraction(extraction_id, status="confirmed", confirmed_at=now)
    return _row_to_out(db.get_extraction(extraction_id))


@router.post("/{extraction_id}/reextract", status_code=202)
def reextract(extraction_id: int) -> dict[str, Any]:
    """已确认的抽取重新抽取：旧结果保留为历史，生成新抽取记录。"""
    row = db.get_extraction(extraction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="抽取结果不存在")
    if row["status"] != "confirmed":
        raise HTTPException(status_code=409, detail="仅已确认的抽取结果可重新抽取")
    try:
        task_id = schedule_extract(row["doc_id"], row["schema_id"])
    except ExtractionError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e
    return {"task_id": task_id, "task": _task_out(db.get_task(task_id))}


@router.get("/{extraction_id}/export")
def export_extraction(extraction_id: int, format: str = "json") -> Response:
    if format not in EXPORT_FORMATS:
        raise HTTPException(status_code=422, detail="format 仅支持 json/excel/markdown")
    row = db.get_extraction(extraction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="抽取结果不存在")
    content, media_type, filename = build_export(row, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )