"""会话与问答 API（M3）：会话 CRUD、消息历史、SSE 流式问答。

对应需求文档 FR-04 / FR-11 / §7.3-7.4：
- POST /api/documents/{doc_id}/chat（stream=true 返回 text/event-stream）
- 会话自动创建（标题取首问前 20 字）；无 Key 时规则问答器降级
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.llm.client import LLMError
from app.models import ChatRequest, Citation, MessageOut, SessionOut
from app.services import qa
from app.services import settings as settings_svc
from app.storage import db

sessions_router = APIRouter(prefix="/api/sessions", tags=["sessions"])
chat_router = APIRouter(prefix="/api/documents", tags=["chat"])


def _session_out(row) -> SessionOut:
    return SessionOut(
        id=row["id"],
        title=row["title"],
        doc_ids=db.jloads(row["doc_ids"], []),
        created_at=row["created_at"],
    )


def _msg_out(row) -> MessageOut:
    raw = db.jloads(row["citations_json"], [])
    citations = [Citation(**c) for c in raw if isinstance(c, dict)]
    return MessageOut(
        id=row["id"],
        session_id=row["session_id"],
        role=row["role"],
        content=row["content"],
        citations=citations,
        source=row["source"] or "llm",
        created_at=row["created_at"],
    )


def _history_dicts(session_id: int) -> list[dict[str, str]]:
    rows = db.list_messages(session_id)[-qa.MAX_HISTORY_ROUNDS * 2 :]
    return [
        {"role": r["role"], "content": r["content"]}
        for r in rows
        if r["role"] in ("user", "assistant")
    ]


@sessions_router.get("")
def list_sessions() -> list[SessionOut]:
    return [_session_out(r) for r in db.list_sessions()]


@sessions_router.post("")
def create_session(body: dict[str, Any]) -> SessionOut:
    doc_ids = [int(d) for d in (body.get("doc_ids") or [])]
    title = str(body.get("title") or "新会话").strip()[:40] or "新会话"
    sid = db.create_session(title, doc_ids)
    return _session_out(db.get_session(sid))


@sessions_router.get("/{session_id}")
def get_session(session_id: int) -> dict[str, Any]:
    row = db.get_session(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "session": _session_out(row),
        "messages": [_msg_out(m) for m in db.list_messages(session_id)],
    }


@sessions_router.delete("/{session_id}")
def delete_session(session_id: int) -> dict[str, Any]:
    if not db.get_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    db.delete_session(session_id)
    return {"deleted": session_id}


def _validate_docs(doc_ids: list[int]) -> None:
    for d in doc_ids:
        row = db.get_document(d)
        if row is None:
            raise HTTPException(status_code=404, detail=f"文档 {d} 不存在")
        if row["status"] != "parsed":
            raise HTTPException(status_code=409, detail="文档尚未完成解析，请稍后重试")


def _sse(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@chat_router.post("/{doc_id}/chat")
def chat(doc_id: int, body: ChatRequest):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")
    doc_ids = list(body.doc_ids) if body.doc_ids else [doc_id]
    if doc_id not in doc_ids:
        doc_ids.insert(0, doc_id)
    _validate_docs(doc_ids)

    if body.session_id is not None:
        if not db.get_session(body.session_id):
            raise HTTPException(status_code=404, detail="会话不存在")
        session_id = body.session_id
    else:
        session_id = db.create_session(question[:20], doc_ids)

    history = _history_dicts(session_id)
    user_msg_id = db.create_message(session_id, "user", question, [], "user")

    hits = qa.retrieve(doc_ids, question)
    retrieval = settings_svc.get_retrieval_settings()
    context = qa.build_context(
        hits, context_limit=int(retrieval.get("context_limit") or 8000)
    )
    client = settings_svc.build_llm_client()
    llm_ok = client.configured

    if not body.stream:
        if llm_ok:
            try:
                content = qa.llm_answer(
                    client, qa.build_messages(question, context, history)
                )
            except LLMError as e:
                raise HTTPException(status_code=502, detail=f"模型调用失败：{e}") from e
            citations = qa.citations_of(hits)
            source = "llm"
        else:
            content, citations = qa.rule_answer(doc_ids, question)
            source = "rule"
        db.create_message(
            session_id,
            "assistant",
            content,
            [c.model_dump() for c in citations],
            source,
        )
        return {
            "session_id": session_id,
            "message_id": user_msg_id,
            "content": content,
            "citations": [c.model_dump() for c in citations],
            "source": source,
        }

    def events() -> Iterator[str]:
        """SSE 事件流：meta → delta×n → done | error。"""
        text_parts: list[str] = []
        saved = False
        citations: list[Citation] = []
        try:
            yield _sse("meta", {"session_id": session_id, "message_id": user_msg_id})
            if llm_ok:
                messages = qa.build_messages(question, context, history)
                for delta in qa.stream_llm_answer(client, messages):
                    text_parts.append(delta)
                    yield _sse("delta", {"text": delta})
                citations = qa.citations_of(hits)
                source = "llm"
            else:
                text, citations = qa.rule_answer(doc_ids, question)
                for piece in qa.chunk_text(text):
                    text_parts.append(piece)
                    yield _sse("delta", {"text": piece})
                source = "rule"
            content = "".join(text_parts)
            db.create_message(
                session_id,
                "assistant",
                content,
                [c.model_dump() for c in citations],
                source,
            )
            saved = True
            yield _sse(
                "done",
                {
                    "citations": [c.model_dump() for c in citations],
                    "source": source,
                },
            )
        except LLMError as e:
            if text_parts:
                db.create_message(
                    session_id,
                    "assistant",
                    "".join(text_parts),
                    [c.model_dump() for c in qa.citations_of(hits)],
                    "llm",
                )
                saved = True
            yield _sse("error", {"message": str(e)})
        finally:
            # 客户端断连时保留已生成的部分回答
            if not saved and text_parts:
                db.create_message(
                    session_id,
                    "assistant",
                    "".join(text_parts),
                    [c.model_dump() for c in qa.citations_of(hits)],
                    "llm",
                )

    return StreamingResponse(events(), media_type="text/event-stream")
