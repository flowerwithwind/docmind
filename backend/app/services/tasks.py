"""异步任务执行器：解析 / 抽取任务（线程池执行，避免阻塞请求线程与事件循环）。"""

from __future__ import annotations

import asyncio

from app.services.chunker import attach_chunk_ids, build_chunks, build_tree
from app.services.compare import CompareError, compare_documents
from app.services.extraction import ExtractionError, extract_document
from app.services.parser import ParseError, parse_document
from app.services.retrieval import INDEX
from app.storage import db
from app.storage.files import file_path
from app.utils.logging import get_logger

logger = get_logger("tasks")


def schedule_parse(doc_id: int) -> int:
    """创建解析任务并后台执行，返回 task_id。"""
    task_id = db.create_task("parse", {"doc_id": doc_id})
    _spawn(run_parse(task_id, doc_id))
    return task_id


def schedule_extract(doc_id: int, schema_id: int) -> int:
    """创建抽取任务并后台执行；同文档 + Schema 已有进行中任务时抛 ExtractionError(409)。"""
    if _has_active_extract(doc_id, schema_id):
        raise ExtractionError("该文档正在抽取同一 Schema，请稍后重试", 409)
    task_id = db.create_task("extract", {"doc_id": doc_id, "schema_id": schema_id})
    _spawn(run_extract(task_id, doc_id, schema_id))
    return task_id


def _has_active_extract(doc_id: int, schema_id: int) -> bool:
    for row in db.list_tasks(kind="extract", limit=100):
        if row["status"] not in ("pending", "running"):
            continue
        payload = db.jloads(row["payload_json"], {})
        if payload.get("doc_id") == doc_id and payload.get("schema_id") == schema_id:
            return True
    return False


def _spawn(coro) -> None:
    """在独立守护线程中执行协程，避免阻塞请求线程 / 事件循环。"""
    import threading

    def _runner() -> None:
        asyncio.run(coro)

    threading.Thread(target=_runner, daemon=True).start()


# ---------------------------------------------------------------- parse

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
        c.update(
            {
                "doc_id": doc_id,
                "created_at": db.now_iso(),
            }
        )
    db.insert_chunks(chunks)
    INDEX.drop(doc_id)  # rebuild in-memory index
    db.update_document(
        doc_id,
        status="parsed",
        parse_error=None,
        page_count=result["page_count"],
        char_count=result["char_count"],
        chunk_count=len(chunks),
        pages_json=db.jdumps(result["pages"]),
        tree_json=db.jdumps(tree),
    )
    return {"chunk_count": len(chunks), "page_count": result["page_count"]}


async def run_parse(task_id: int, doc_id: int) -> None:
    try:
        res = await asyncio.to_thread(_parse_work, task_id, doc_id)
        db.update_task(
            task_id,
            status="succeeded",
            progress=100,
            message="解析完成",
            result_json=db.jdumps(res),
            finished_at=db.now_iso(),
        )
    except ParseError as e:
        db.update_document(doc_id, status="failed", parse_error=str(e))
        db.update_task(task_id, status="failed", error=str(e), finished_at=db.now_iso())
    except Exception as e:
        logger.exception("parse task failed")
        db.update_document(doc_id, status="failed", parse_error=f"解析异常：{e}")
        db.update_task(task_id, status="failed", error=f"解析异常：{e}", finished_at=db.now_iso())


# ---------------------------------------------------------------- extract

def _extract_work(task_id: int, doc_id: int, schema_id: int) -> dict:
    db.update_task(task_id, status="running", progress=10, message="开始抽取")
    res = extract_document(doc_id, schema_id)
    db.update_task(task_id, progress=80, message="保存抽取结果")
    ext_id = db.create_extraction(doc_id, schema_id, source=res["source"])
    db.update_extraction(
        ext_id,
        data_json=db.jdumps(res["data"]),
        confidence_json=db.jdumps(res["confidence"]),
        field_status_json=db.jdumps(res["field_status"]),
        citations_json=db.jdumps(res["citations"]),
        llm_raw=res.get("llm_raw"),
        model_json=db.jdumps(res["data"]),
    )
    counts = {
        s: sum(1 for v in res["field_status"].values() if v == s)
        for s in ("extracted", "unsure", "missing", "invalid")
    }
    return {
        "extraction_id": ext_id,
        "source": res["source"],
        "field_count": len(res["data"]),
        **counts,
    }


async def run_extract(task_id: int, doc_id: int, schema_id: int) -> None:
    try:
        res = await asyncio.to_thread(_extract_work, task_id, doc_id, schema_id)
        db.update_task(
            task_id,
            status="succeeded",
            progress=100,
            message="抽取完成",
            result_json=db.jdumps(res),
            finished_at=db.now_iso(),
        )
    except ExtractionError as e:
        db.update_task(task_id, status="failed", error=str(e), finished_at=db.now_iso())
    except Exception as e:
        logger.exception("extract task failed")
        db.update_task(task_id, status="failed", error=f"抽取异常：{e}", finished_at=db.now_iso())

# ---------------------------------------------------------------- compare

def schedule_compare(doc_a_id: int, doc_b_id: int, schema_id: int) -> int:
    """创建对比任务并后台执行，返回 task_id。"""
    task_id = db.create_task("compare", {
        "doc_a_id": doc_a_id, "doc_b_id": doc_b_id, "schema_id": schema_id,
    })
    _spawn(run_compare(task_id, doc_a_id, doc_b_id, schema_id))
    return task_id


def _compare_work(task_id: int, doc_a_id: int, doc_b_id: int, schema_id: int) -> dict:
    db.update_task(task_id, status="running", progress=15, message="开始对比")
    result = compare_documents(doc_a_id, doc_b_id, schema_id)
    db.update_task(task_id, progress=85, message="保存对比结果")
    compare_id = db.create_compare(doc_a_id, doc_b_id, schema_id, result)
    return {
        "compare_id": compare_id,
        "field_count": len(result["field_diff"]),
        "changed_fields": sum(1 for d in result["field_diff"] if d["status"] == "changed"),
        "section_diff_count": len(result["section_diff"]),
    }


async def run_compare(task_id: int, doc_a_id: int, doc_b_id: int, schema_id: int) -> None:
    try:
        res = await asyncio.to_thread(_compare_work, task_id, doc_a_id, doc_b_id, schema_id)
        db.update_task(
            task_id,
            status="succeeded",
            progress=100,
            message="对比完成",
            result_json=db.jdumps(res),
            finished_at=db.now_iso(),
        )
    except CompareError as e:
        db.update_task(task_id, status="failed", error=str(e), finished_at=db.now_iso())
    except Exception as e:
        logger.exception("compare task failed")
        db.update_task(task_id, status="failed", error=f"对比异常：{e}", finished_at=db.now_iso())


# ---------------------------------------------------------------- demo load

def schedule_demo_load(kind: str, doc_id: int) -> int:
    """创建样例加载任务（文档与文件已在 API 层创建），任务内执行解析。"""
    task_id = db.create_task("demo_load", {"kind": kind, "doc_id": doc_id})
    _spawn(run_demo_load(task_id, doc_id))
    return task_id


async def run_demo_load(task_id: int, doc_id: int) -> None:
    db.update_task(task_id, status="running", progress=10, message="解析样例文档")
    try:
        parse_task_id = db.create_task("parse", {"doc_id": doc_id, "source": "demo"})
        await run_parse(parse_task_id, doc_id)
        parse_task = db.get_task(parse_task_id)
        if parse_task["status"] != "succeeded":
            raise RuntimeError(parse_task["error"] or "样例解析失败")
        db.update_task(
            task_id,
            status="succeeded",
            progress=100,
            message="样例加载完成",
            result_json=db.jdumps({"doc_id": doc_id, "parse_task_id": parse_task_id}),
            finished_at=db.now_iso(),
        )
    except Exception as e:
        logger.exception("demo load task failed")
        db.update_task(task_id, status="failed", error=f"样例加载失败：{e}", finished_at=db.now_iso())
