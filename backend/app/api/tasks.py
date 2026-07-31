"""任务 API（轮询进度）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models import TaskOut
from app.storage import db

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _row_to_out(row) -> TaskOut:
    return TaskOut(
        id=row["id"], kind=row["kind"], status=row["status"], progress=row["progress"],
        message=row["message"] or "", result_json=row["result_json"],
        error=row["error"], created_at=row["created_at"], finished_at=row["finished_at"],
    )


@router.get("")
def list_tasks(kind: str = "", limit: int = 50) -> list[TaskOut]:
    return [_row_to_out(r) for r in db.list_tasks(kind=kind, limit=min(limit, 200))]


@router.get("/{task_id}")
def get_task(task_id: int) -> TaskOut:
    row = db.get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _row_to_out(row)
