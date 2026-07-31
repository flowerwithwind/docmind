"""抽取服务（FR-06）：LLM 分批抽取 + JSON 修复 + 置信度，规则抽取器降级。

流程：检索相关块（每字段 top 4，合并 top 12）→ 分批（≤8 字段）送入 LLM
→ JSON 输出解析（失败重试 2 次）→ 字段归一化校验 → 置信度（自评 + 规则冲突折半）。
无 Key 或 LLM 调用失败时按批回退规则抽取器。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.fallback.extractor import extract_by_rules
from app.llm.client import LLMError, LLMNotConfigured
from app.services import qa
from app.services import settings as settings_svc
from app.storage import db
from app.utils.text import normalize_value

BATCH_SIZE = 8
MAX_RETRIES = 2
RETRIEVE_TOP_K = 12
MIN_CONFIDENCE = 0.5  # 低于此置信度标记 unsure

EXTRACT_SYSTEM = (
    "你是 DocMind 文档抽取引擎，负责从文档片段中抽取结构化字段。\n"
    "规则：\n"
    "1. 只能依据给定的文档片段抽取，片段中没有的信息输出 null。\n"
    "2. 只输出 JSON 对象，不要输出任何解释、markdown 代码块或多余文字。\n"
    "3. JSON 格式：{\"<field_key>\": {\"value\": <字段值>, \"confidence\": <0到1的自评置信度>}}。\n"
    "4. 数字字段输出数字（不要带单位），日期字段输出 YYYY-MM-DD，枚举字段严格使用给定枚举值。"
)

REPAIR_PROMPT = (
    "上一次输出不是合法 JSON，请重新输出且只输出一个 JSON 对象"
    "（不要 markdown 代码块，不要多余文字）。"
)


class ExtractionError(RuntimeError):
    """抽取业务错误；status_code 供 API 层映射 HTTP 状态。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------- 入口

def extract_document(doc_id: int, schema_id: int) -> dict[str, Any]:
    """执行一次抽取（同步工作函数，任务线程内调用）。"""
    doc = db.get_document(doc_id)
    if doc is None:
        raise ExtractionError("文档不存在", 404)
    if doc["status"] != "parsed":
        raise ExtractionError("文档尚未完成解析，请稍后重试", 409)
    schema = db.get_schema(schema_id)
    if schema is None:
        raise ExtractionError("Schema 不存在", 404)
    fields = db.jloads(schema["fields_json"], [])
    if not fields:
        raise ExtractionError("Schema 未定义字段", 422)

    client = settings_svc.build_llm_client()
    if client.configured:
        try:
            return _extract_with_llm(doc_id, fields, client)
        except LLMNotConfigured:
            pass  # 防御性降级到规则模式
    return _extract_with_rules(doc_id, fields)


# ---------------------------------------------------------------- 规则模式

def _extract_with_rules(doc_id: int, fields: list[dict[str, Any]]) -> dict[str, Any]:
    chunks = [dict(c) for c in db.list_chunks(doc_id)]
    result = extract_by_rules(doc_id, fields, chunks)
    result["llm_raw"] = None
    return result


# ---------------------------------------------------------------- LLM 模式

def _extract_with_llm(
    doc_id: int, fields: list[dict[str, Any]], client: Any
) -> dict[str, Any]:
    hits = _retrieve_hits(doc_id, fields)
    data: dict[str, Any] = {}
    confidence: dict[str, float] = {}
    field_status: dict[str, str] = {}
    citations: dict[str, list[dict[str, Any]]] = {}
    raw_outputs: list[str] = []

    for batch in _batches(fields, BATCH_SIZE):
        messages = _build_messages(hits, batch)
        try:
            parsed, raw = _ask_json(client, messages)
        except LLMError:
            # 模型调用失败：该批回退规则抽取器，保证演示闭环
            _merge_rule_items(
                data, confidence, field_status, citations,
                _rules_for_fields(doc_id, batch),
            )
            continue
        raw_outputs.append(raw)
        if parsed is None:
            # JSON 重试仍失败：该批字段标记 invalid
            for f in batch:
                _mark(data, confidence, field_status, citations, f["key"],
                      None, 0.3, "invalid")
            continue
        for f in batch:
            key = f["key"]
            entry = parsed.get(key)
            if not isinstance(entry, dict) or "value" not in entry:
                _mark(data, confidence, field_status, citations, key,
                      None, 0.0, "missing")
                continue
            c = _to_confidence(entry.get("confidence"))
            normalized, ok = normalize_value(f, entry.get("value"))
            if not ok:
                _mark(data, confidence, field_status, citations, key,
                      None, round(c * 0.5, 3), "invalid")
            elif normalized is None:
                _mark(data, confidence, field_status, citations, key,
                      None, 0.0, "missing")
            else:
                _mark(data, confidence, field_status, citations, key,
                      normalized, round(c, 3),
                      "extracted" if c >= MIN_CONFIDENCE else "unsure")
            citations[key] = _field_citations(hits, key)

    if not raw_outputs:
        # 全部批次调用失败：整体降级为规则模式，保证演示闭环（source=rule）
        result = _extract_with_rules(doc_id, fields)
        result["llm_raw"] = None
        return result
    return {
        "data": data,
        "confidence": confidence,
        "field_status": field_status,
        "citations": citations,
        "source": "llm",
        "llm_raw": "\n".join(raw_outputs)[:20000],
    }


def _retrieve_hits(
    doc_id: int, fields: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """按字段标签/描述逐字段检索，返回 field_key -> 命中块列表。"""
    out: dict[str, list[dict[str, Any]]] = {}
    for f in fields:
        query = " ".join(
            x for x in (f.get("label"), f.get("description"), f.get("prompt_hint"))
            if x
        )
        out[f["key"]] = qa.retrieve([doc_id], query, top_k=4)
    return out


def _build_messages(
    hits: dict[str, list[dict[str, Any]]], batch: list[dict[str, Any]]
) -> list[dict[str, str]]:
    context = _build_batch_context(hits, batch)
    spec = _fields_spec(batch)
    return [
        {"role": "system", "content": EXTRACT_SYSTEM},
        {
            "role": "user",
            "content": (
                f"文档片段：\n{context}\n\n字段定义：\n{spec}\n"
                "请抽取以上字段并输出 JSON。"
            ),
        },
    ]


def _build_batch_context(
    hits: dict[str, list[dict[str, Any]]], batch: list[dict[str, Any]]
) -> str:
    """合并本批字段的命中块，按相关度取前 RETRIEVE_TOP_K。"""
    seen: dict[int, dict[str, Any]] = {}
    for f in batch:
        for h in hits.get(f["key"], []):
            seen.setdefault(h["id"], h)
    ordered = sorted(
        seen.values(), key=lambda h: float(h.get("_raw", 0)), reverse=True
    )[:RETRIEVE_TOP_K]
    return qa.build_context(ordered, context_limit=6000)


def _fields_spec(fields: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for f in fields:
        parts = [
            f"- {f['key']}（{f.get('label')}，{f.get('type')}，"
            f"{'必填' if f.get('required') else '可选'}）"
        ]
        if f.get("description"):
            parts.append(f"说明：{f['description']}")
        if f.get("example"):
            parts.append(f"示例：{f['example']}")
        if f.get("enum"):
            parts.append(f"枚举：{' / '.join(f['enum'])}")
        lines.append("；".join(parts))
    return "\n".join(lines)


def _ask_json(client: Any, messages: list[dict[str, str]]) -> tuple[dict | None, str]:
    """带重试的 JSON 抽取；返回 (解析结果, 最后一次原始输出)。"""
    raw = ""
    current = list(messages)
    for attempt in range(MAX_RETRIES + 1):
        raw = client.chat(current, json_mode=True)
        parsed = _parse_json(raw)
        if parsed is not None:
            return parsed, raw
        if attempt < MAX_RETRIES:
            current = current + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": REPAIR_PROMPT},
            ]
    return None, raw


def _parse_json(raw: str) -> dict | None:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _to_confidence(value: object) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.7
    return min(max(c, 0.0), 1.0)


def _field_citations(
    hits: dict[str, list[dict[str, Any]]], key: str
) -> list[dict[str, Any]]:
    return [c.model_dump() for c in qa.citations_of(hits.get(key, [])[:3])]


def _rules_for_fields(
    doc_id: int, fields: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """对给定字段集合执行规则抽取，返回 {key: {value, confidence, status, citations}}。"""
    chunks = [dict(c) for c in db.list_chunks(doc_id)]
    res = extract_by_rules(doc_id, fields, chunks)
    return {
        f["key"]: {
            "value": res["data"][f["key"]],
            "confidence": res["confidence"][f["key"]],
            "status": res["field_status"][f["key"]],
            "citations": res["citations"][f["key"]],
        }
        for f in fields
    }


def _merge_rule_items(
    data: dict[str, Any],
    confidence: dict[str, float],
    field_status: dict[str, str],
    citations: dict[str, list[dict[str, Any]]],
    items: dict[str, dict[str, Any]],
) -> None:
    for key, item in items.items():
        data[key] = item["value"]
        confidence[key] = item["confidence"]
        field_status[key] = item["status"]
        citations[key] = item["citations"]


def _mark(
    data: dict[str, Any],
    confidence: dict[str, float],
    field_status: dict[str, str],
    citations: dict[str, list[dict[str, Any]]],
    key: str,
    value: object,
    conf: float,
    status: str,
) -> None:
    data[key] = value
    confidence[key] = conf
    field_status[key] = status
    citations.setdefault(key, [])


def _batches(
    fields: list[dict[str, Any]], size: int = BATCH_SIZE
) -> list[list[dict[str, Any]]]:
    return [fields[i : i + size] for i in range(0, len(fields), size)]