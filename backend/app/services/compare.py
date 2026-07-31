"""对比服务（M5/FR-08）：同 Schema 两份文档的字段级 diff 与章节相似度。

字段状态：same / changed / only_a / only_b / both_missing；
数值 changed 时计算 delta_pct（如金额 +8.3%）。
章节相似度：按 section_path 对齐，正文字符 bigram Jaccard ∈[0,1]；
<0.6 视为 changed，>=0.6 视为 same。
"""
from __future__ import annotations

import re
from typing import Any

from app.storage import db

SECTION_SIMILARITY_THRESHOLD = 0.6


class CompareError(RuntimeError):
    """对比业务错误；status_code 供 API 层映射 HTTP 状态。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _bigrams(text: str) -> set[str]:
    t = _norm(text)
    return {t[i : i + 2] for i in range(max(0, len(t) - 1))}


def content_similarity(a: str, b: str) -> float:
    """归一化文本相似度（字符 bigram Jaccard），空对空视为 1.0。"""
    sa, sb = _bigrams(a), _bigrams(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return round(len(sa & sb) / len(sa | sb), 3)


def _delta_pct(a: object, b: object) -> float | None:
    try:
        na, nb = float(a), float(b)
    except (TypeError, ValueError):
        return None
    if na == 0:
        return None
    return round((nb - na) / abs(na) * 100, 1)


def compare_documents(doc_a_id: int, doc_b_id: int, schema_id: int) -> dict[str, Any]:
    """对比两份文档（同一 Schema），返回 {field_diff, section_diff, summary, source}。"""
    doc_a = db.get_document(doc_a_id)
    doc_b = db.get_document(doc_b_id)
    if doc_a is None or doc_b is None:
        raise CompareError("对比文档不存在", 404)
    schema = db.get_schema(schema_id)
    if schema is None:
        raise CompareError("Schema 不存在", 404)
    ext_a = db.get_latest_extraction(doc_a_id, schema_id)
    ext_b = db.get_latest_extraction(doc_b_id, schema_id)
    if ext_a is None or ext_b is None:
        raise CompareError("参与对比的文档需先完成同 Schema 抽取", 409)

    fields = db.jloads(schema["fields_json"], [])
    data_a = db.jloads(ext_a["data_json"], {})
    data_b = db.jloads(ext_b["data_json"], {})

    field_diff: list[dict[str, Any]] = []
    changed_labels: list[str] = []
    for f in fields:
        key = f["key"]
        label = f.get("label") or key
        va, vb = data_a.get(key), data_b.get(key)
        missing_a = va is None or va == ""
        missing_b = vb is None or vb == ""
        if missing_a and missing_b:
            status, delta = "both_missing", None
        elif missing_a:
            status, delta = "only_b", None
        elif missing_b:
            status, delta = "only_a", None
        else:
            same = va == vb
            if not same and f.get("type") == "number":
                try:
                    same = abs(float(va) - float(vb)) < 1e-9
                except (TypeError, ValueError):
                    pass
            if same:
                status, delta = "same", None
            else:
                status, delta = "changed", _delta_pct(va, vb)
                changed_labels.append(label)
        field_diff.append({
            "key": key, "label": label, "value_a": va, "value_b": vb,
            "status": status, "delta_pct": delta,
        })

    section_diff = _section_diff(doc_a_id, doc_b_id)
    summary = _build_summary(field_diff, section_diff)
    return {
        "field_diff": field_diff,
        "section_diff": section_diff,
        "summary": summary,
        "source": "rule",
    }


def _section_diff(doc_a_id: int, doc_b_id: int) -> list[dict[str, Any]]:
    def group(doc_id: int) -> dict[str, str]:
        out: dict[str, list[str]] = {}
        for c in db.list_chunks(doc_id):
            if c["kind"] == "table":
                continue  # 表格以抽取字段体现，正文相似度不含表格
            title = (c["section_path"] or c["title"] or "").strip() or "正文"
            out.setdefault(title, []).append(c["content"] or "")
        return {t: "".join(parts) for t, parts in out.items()}

    ga, gb = group(doc_a_id), group(doc_b_id)
    result: list[dict[str, Any]] = []
    for title in sorted(set(ga) | set(gb)):
        if title in ga and title in gb:
            sim = content_similarity(ga[title], gb[title])
            status = "same" if sim >= SECTION_SIMILARITY_THRESHOLD else "changed"
        elif title in ga:
            sim, status = 0.0, "removed"
        else:
            sim, status = 0.0, "added"
        result.append({"title": title, "status": status, "similarity": sim})
    return result


def _build_summary(field_diff: list[dict[str, Any]], section_diff: list[dict[str, Any]]) -> str:
    changed = [d for d in field_diff if d["status"] == "changed"]
    only_a = [d for d in field_diff if d["status"] == "only_a"]
    only_b = [d for d in field_diff if d["status"] == "only_b"]
    sec_changed = [d for d in section_diff if d["status"] != "same"]
    parts = [f"共对比 {len(field_diff)} 个字段"]
    if changed:
        labels = "、".join(d["label"] for d in changed[:5])
        more = f" 等 {len(changed)} 项" if len(changed) > 5 else ""
        parts.append(f"{len(changed)} 个字段发生变化：{labels}{more}")
    if only_a:
        parts.append(f"{len(only_a)} 个字段仅文档 A 有值")
    if only_b:
        parts.append(f"{len(only_b)} 个字段仅文档 B 有值")
    if sec_changed:
        titles = "、".join(d["title"] for d in sec_changed[:5])
        more = f" 等 {len(sec_changed)} 处" if len(sec_changed) > 5 else ""
        parts.append(f"章节差异 {len(sec_changed)} 处：{titles}{more}")
    else:
        parts.append("章节内容基本一致")
    return "；".join(parts)
