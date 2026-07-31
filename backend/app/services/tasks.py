"""异步任务执行器：解析任务（线程池执行，避免阻塞事件循环）。"""
from __future__ import annotations

import asyncio

from app.services.chunker import attach_chunk_ids, build_chunks, build_tree
from app.services.parser import ParseError, parse_document
from app.storage import db
from app.storage.files import file_path
from app.utils.logging import get_logger

logger = get_logger("tasks")


def schedule_parse(doc_id: int) -> int:
    """创建解析任务并后台执行，返回 task_id。"""
    task_id = db.create_task("parse", {"doc_id": doc_id})
    _spawn(run_parse(task_id, doc_id))
    return task_id


def _spawn(coro) -> None:
    """在独立守护线程中执行协程，避免阻塞请求线程/事件循环。"""
    import threading

    def _runner() -> None:
        asyncio.run(coro)

    threading.Thread(target=_runner, daemon=True).start()


def _parse_work(task_id: int, doc_id: int) -> dict:
    db.update_task(task_id, status="running", progress=5, message="开始解析")
    db.update_document(doc_id, status="parsing", parse_error=None)
    doc = db.get_document(doc_id)
    if doc is None:
        raise ParseError("文档不存在")
    result = parse_document(file_path(doc["filename"]), doc["ext"])
    db.update_task(task_id, progress=55, message="智能分块与结构树")
    chunks = build_chunks(result["pages"])
    tree = build_tree(result["pages"])
    attach_chunk_ids(tree, chunks)
    db.delete_chunks(doc_id)
    for c in chunks:
        c.setdefault("section_path", None)
        c.setdefault("title", None)
        c.setdefault("image_path", None)
        c.update({
            "doc_id": doc_id,
            "created_at": db.now_iso(),
        })
    db.insert_chunks(chunks)
    db.update_document(
        doc_id, status="parsed", parse_error=None,
        page_count=result["page_count"], char_count=result["char_count"],
        chunk_count=len(chunks), pages_json=db.jdumps(result["pages"]),
        tree_json=db.jdumps(tree),
    )
    return {"chunk_count": len(chunks), "page_count": result["page_count"]}


async def run_parse(task_id: int, doc_id: int) -> None:
    try:
        res = await asyncio.to_thread(_parse_work, task_id, doc_id)
        db.update_task(task_id, status="succeeded", progress=100,
                       message="解析完成", result_json=db.jdumps(res))
    except ParseError as e:
        db.update_document(doc_id, status="failed", parse_error=str(e))
        db.update_task(task_id, status="failed", error=str(e))
    except Exception as e:
        logger.exception("parse task failed")
        db.update_document(doc_id, status="failed", parse_error=f"解析异常：{e}")
        db.update_task(task_id, status="failed", error=f"解析异常：{e}")
