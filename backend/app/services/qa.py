"""问答编排：检索 → 上下文组装 → LLM 流式生成 / 规则问答器降级。

对应需求文档 FR-04：引用溯源、SSE 流式输出、多轮历史、无 Key 降级。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.models import Citation
from app.services import settings as settings_svc
from app.services.retrieval import INDEX, RULE_MIN_SCORE
from app.utils.text import token_estimate, truncate

NO_ANSWER = "未在文档中找到相关信息"

SYSTEM_PROMPT = (
    "你是 DocMind 文档智能助手，负责基于用户提供的文档片段回答问题。\n"
    "规则：\n"
    "1. 只依据文档片段回答；若片段中没有相关信息，必须回答“未在文档中找到相关信息”，禁止编造。\n"
    "2. 引用来源时在句末使用 [1] [2] 角标，编号对应文档片段中的编号。\n"
    "3. 使用与用户提问相同的语言回答；中文回答使用简体中文。\n"
    "4. 回答尽量简洁，先给结论再给依据。"
)

MAX_HISTORY_ROUNDS = 8


def retrieve(
    doc_ids: list[int], question: str, top_k: int | None = None
) -> list[dict[str, Any]]:
    """按全局检索设置执行多文档检索，返回带 _score 的块列表。"""
    r = settings_svc.get_retrieval_settings()
    k = int(top_k or r.get("top_k") or 6)
    return INDEX.search(
        doc_ids,
        question,
        top_k=k,
        rrf_k=int(r.get("rrf_k") or 60),
        dense=bool(r.get("dense_enabled", False)),
    )


def citations_of(chunks: list[dict[str, Any]]) -> list[Citation]:
    """块列表 → 引用列表（页面/章节/摘要）。"""
    return [
        Citation(
            chunk_id=c["id"],
            page=c.get("page"),
            section=(c.get("section_path") or c.get("title") or ""),
            snippet=truncate((c.get("content") or "").replace("\n", " "), 120),
        )
        for c in chunks
    ]


def build_context(hits: list[dict[str, Any]], context_limit: int = 8000) -> str:
    """组装带编号与元信息的上下文，按 token 预算裁剪。"""
    parts: list[str] = []
    total = 0
    for i, h in enumerate(hits, 1):
        meta: list[str] = []
        if h.get("page"):
            meta.append(f"第{h['page']}页")
        sec = h.get("section_path") or h.get("title")
        if sec:
            meta.append(str(sec))
        head = f"[{i}]" + (f"（{'，'.join(meta)}）" if meta else "")
        block = f"{head}\n{(h.get('content') or '').strip()}"
        total += token_estimate(block)
        if total > context_limit and parts:
            break
        parts.append(block)
    return "\n\n".join(parts)


def build_messages(
    question: str, context: str, history: list[dict[str, str]] | None = None
) -> list[dict[str, str]]:
    """组装 LLM 消息：system + 最近 8 轮历史 + 当前问题。"""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-MAX_HISTORY_ROUNDS * 2 :])
    messages.append(
        {"role": "user", "content": f"文档片段：\n{context}\n\n问题：{question}"}
    )
    return messages


def rule_answer(
    doc_ids: list[int],
    question: str,
    top_k: int | None = None,
    threshold: float = RULE_MIN_SCORE,
) -> tuple[str, list[Citation]]:
    """规则问答器：检索命中块直接作为答案片段返回（无 Key 演示降级）。

    最高分低于阈值时回答"未在文档中找到相关信息"，不编造。
    """
    hits = retrieve(doc_ids, question, top_k=top_k)
    if not hits or float(hits[0].get("_raw", 0)) < threshold:
        return NO_ANSWER, []
    parts = [f"[{i}] {(h.get('content') or '').strip()}" for i, h in enumerate(hits, 1)]
    return "\n\n".join(parts), citations_of(hits)


def stream_llm_answer(client, messages: list[dict[str, str]]) -> Iterator[str]:
    """LLM 流式生成（透传客户端增量）。"""
    yield from client.chat_stream(messages)


def llm_answer(client, messages: list[dict[str, str]]) -> str:
    """LLM 一次性生成（非流式路径）。"""
    return client.chat(messages, json_mode=False)


def chunk_text(text: str, size: int = 24) -> Iterator[str]:
    """把完整文本切成小段，模拟流式输出（规则模式）。"""
    for i in range(0, len(text), size):
        yield text[i : i + size]
