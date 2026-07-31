"""Schema 管理 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models import SchemaIn, SchemaOut
from app.storage import db

router = APIRouter(prefix="/api/schemas", tags=["schemas"])


def _row_to_out(row) -> SchemaOut:
    return SchemaOut(
        id=row["id"], key=row["key"], name=row["name"], description=row["description"] or "",
        fields=db.jloads(row["fields_json"], []), is_builtin=bool(row["is_builtin"]),
        created_at=row["created_at"],
    )


@router.get("")
def list_schemas() -> list[SchemaOut]:
    return [_row_to_out(r) for r in db.list_schemas()]


@router.post("", status_code=201)
def create_schema(body: SchemaIn) -> SchemaOut:
    if db.get_schema_by_key(body.key):
        raise HTTPException(status_code=409, detail=f"Schema key '{body.key}' 已存在")
    sid = db.create_schema(body.key, body.name, body.description, [f.model_dump() for f in body.fields])
    return _row_to_out(db.get_schema(sid))


@router.get("/{schema_id}")
def get_schema(schema_id: int) -> SchemaOut:
    row = db.get_schema(schema_id)
    if not row:
        raise HTTPException(status_code=404, detail="Schema 不存在")
    return _row_to_out(row)


@router.put("/{schema_id}")
def update_schema(schema_id: int, body: SchemaIn) -> SchemaOut:
    row = db.get_schema(schema_id)
    if not row:
        raise HTTPException(status_code=404, detail="Schema 不存在")
    if row["is_builtin"]:
        raise HTTPException(status_code=403, detail="内置 Schema 不可修改，可新建副本")
    db.update_schema(schema_id, body.name, body.description, [f.model_dump() for f in body.fields])
    return _row_to_out(db.get_schema(schema_id))


@router.delete("/{schema_id}", status_code=204)
def delete_schema(schema_id: int) -> None:
    row = db.get_schema(schema_id)
    if not row:
        raise HTTPException(status_code=404, detail="Schema 不存在")
    if row["is_builtin"]:
        raise HTTPException(status_code=403, detail="内置 Schema 不可删除")
    if db.count_extractions_for_schema(schema_id) > 0:
        raise HTTPException(status_code=409, detail="该 Schema 已有抽取结果，不可删除")
    db.delete_schema(schema_id)
