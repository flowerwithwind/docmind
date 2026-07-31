"""表格问答 API（B2）：NL2SQL 链路入口。

- POST /api/qa/table：表格来源标识（table_id / doc_id）或内联表结构 + 自然语言问题
- GET  /api/qa/tables：已注册可查询表列表（演示/调试辅助）
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.models import TableQAOut, TableQARequest
from app.services import table_qa as table_qa_svc
from app.services import tables as table_convert
from app.services.table_store import TableError, table_store

router = APIRouter(prefix="/api/qa", tags=["table-qa"])


def _resolve_table(body: TableQARequest) -> tuple[Any, list[str]]:
    """解析表格来源：doc_id 抽取文档表格块 / table_id 引用 / table 内联结构。"""
    if body.doc_id is not None:
        try:
            refs = table_convert.register_from_doc(body.doc_id)
        except TableError as e:
            raise HTTPException(status_code=e.status_code, detail=str(e)) from e
        return refs[0], [r.id for r in refs]
    if body.table_id:
        try:
            table = table_store.get(body.table_id)
        except TableError as e:
            raise HTTPException(status_code=e.status_code, detail=str(e)) from e
        return table, [table.id]
    if body.table is not None:
        columns = body.table.get("columns") or []
        rows = body.table.get("rows") or []
        name = str(body.table.get("name") or "内联表格")
        try:
            ref = table_store.register(columns, rows, name=name, source="inline")
        except TableError as e:
            raise HTTPException(status_code=e.status_code, detail=str(e)) from e
        return ref, [ref.id]
    raise HTTPException(status_code=400, detail="请提供 table_id / doc_id / table 之一")


@router.post("/table")
def table_qa(body: TableQARequest) -> TableQAOut:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")
    table, table_ids = _resolve_table(body)
    result = table_qa_svc.answer_table(table, question)
    result["metrics"]["table_id"] = table.id
    result["tables"] = table_ids
    return TableQAOut(**result)


@router.get("/tables")
def list_tables() -> list[dict[str, Any]]:
    return table_store.list_tables()
