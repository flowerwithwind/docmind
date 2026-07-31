"""表格问答服务（B2）：意图识别 → 表结构上下文 → LLM 生成 SQL → 白名单校验 → 执行 → 自纠错（重试 1 次）→ 规则降级。

输出约定（与接口一致）：
- source：llm / demo（无 Key 或 LLM 失败时降级为 demo 规则引擎）
- metrics：elapsed_ms / attempts / tokens / intent / fallback_reason 等
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from app.llm.client import LLMError, LLMNotConfigured
from app.services import settings as settings_svc
from app.services.table_store import (
    MAX_ROWS,
    SqlExecutionError,
    SqlValidationError,
    TableRef,
    ensure_limit,
    table_store,
    validate_sql,
)
from app.utils.logging import get_logger
from app.utils.text import clean_text, token_estimate, tokenize

logger = get_logger("table_qa")

MAX_LLM_ATTEMPTS = 2  # 自纠错：失败重试 1 次

AGG_KEYWORDS = (
    "总数", "合计", "总和", "平均", "均值", "最大", "最小", "最多", "最少",
    "最高", "最低", "求和", "统计", "多少", "几个",
)
FILTER_KEYWORDS = (
    "哪些", "列出", "查询", "找出", "显示", "看看", "谁", "哪个", "什么",
    "大于", "小于", "等于", "超过", "不低于", "不高于",
)
_NUMERIC_HINT_COLS = ("额", "金额", "价", "数量", "数", "量", "利润", "收入", "成本", "占比")
_AGG_HINT_WORDS = ("多少", "总额", "合计", "总和", "平均", "均值", "最大", "最小", "最多", "最少")

SYSTEM_PROMPT = (
    "你是 DocMind 表格问答引擎，负责把自然语言问题转换成只读 SQL 并给出简洁中文答案。\n"
    "规则：\n"
    "1. 只能输出单条 SELECT 查询；禁止 INSERT/UPDATE/DELETE/DROP/ALTER/PRAGMA 等任何写操作或危险语句。\n"
    "2. 表名固定为 t；列名必须使用给定的 c1..cN 标识符，禁止使用原始中文列名。\n"
    "3. 若问题涉及筛选/排序/聚合，请直接在 SQL 中完成；结果行数不要超过 100（可自行加 LIMIT 100）。\n"
    "4. 只输出一个 JSON 对象：{\"sql\": \"<SELECT 语句>\", \"answer\": \"<中文简洁答案>\"}，不要输出解释或 markdown 代码块。\n"
    "5. answer 必须基于查询结果用中文回答；若查询结果为空则输出“未查询到结果”。\n"
)


class QaGenerationError(RuntimeError):
    """LLM 生成/自纠错后仍无法得到可执行 SQL。"""


def detect_intent(question: str) -> str:
    """规则意图识别：aggregate（聚合统计）/ filter（筛选列出）/ list（默认全量）。"""
    q = question.lower()
    if any(k in q for k in AGG_KEYWORDS):
        return "aggregate"
    if any(k in q for k in FILTER_KEYWORDS):
        return "filter"
    return "list"


def parse_json(raw: str) -> dict | None:
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


def build_table_schema(table: TableRef) -> str:
    """表结构上下文：安全列名 + 原始列名 + 类型 + 示例值。"""
    lines = [f"表 t（名称：{table.name}），共 {len(table.rows)} 行，列说明："]
    for i, (orig, sql_name, ty) in enumerate(zip(table.columns, table.sql_names, table.types), 1):
        samples = [str(r[i - 1]) for r in table.rows[:2] if i - 1 < len(r)]
        sample = "、".join(samples) if samples else "（无样例）"
        lines.append(f"- {sql_name}：原始列名「{orig}」，类型 {ty.lower()}，示例值 {sample}")
    return "\n".join(lines)


def build_messages(table: TableRef, question: str, intent: str) -> list[dict[str, str]]:
    schema = build_table_schema(table)
    preview = "\n".join(" | ".join(str(c) for c in row) for row in table.rows[:3])
    content = (
        f"表结构：\n{schema}\n\n"
        f"示例数据（前 {min(3, len(table.rows))} 行）：\n{preview}\n\n"
        f"用户问题：{question}\n识别意图：{intent}\n\n"
        "请输出 JSON（不要 markdown 代码块）：{\"sql\": \"...\", \"answer\": \"...\"}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def _repair_prompt(table: TableRef, error: str) -> str:
    return (
        f"上一条 SQL 执行失败：{error}。"
        f"请修正后重新输出 JSON；仅允许单条只读 SELECT，表名 t，列名只能使用 c1..c{len(table.columns)}，"
        "结果不超过 100 行，不要输出解释或 markdown。"
    )


def generate_with_retry(
    client: Any, table: TableRef, question: str, intent: str
) -> dict[str, Any]:
    """LLM 生成 → 校验/执行 → 失败重试 1 次（自纠错）→ 返回可执行结果。"""
    messages = build_messages(table, question, intent)
    tokens = 0
    last_error = ""
    for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
        raw = client.chat(messages, json_mode=True)
        tokens += token_estimate(raw)
        parsed = parse_json(raw)
        sql = str((parsed or {}).get("sql") or "").strip()
        answer = str((parsed or {}).get("answer") or "").strip()
        if not sql:
            last_error = "模型未返回 SQL"
        else:
            try:
                sql = validate_sql(sql)
                sql = ensure_limit(sql, MAX_ROWS)
                columns, rows = table_store.query(table, sql)
                if not answer:
                    answer = f"查询到 {len(rows)} 行结果"
                return {
                    "sql": sql,
                    "answer": answer,
                    "columns": columns,
                    "rows": rows,
                    "attempts": attempt,
                    "tokens": tokens,
                }
            except (SqlValidationError, SqlExecutionError) as e:
                last_error = str(e)
        if attempt < MAX_LLM_ATTEMPTS:
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": _repair_prompt(table, last_error)},
            ]
    raise QaGenerationError(last_error)


# ---------------------------------------------------------------- 规则降级

def _num(value: Any) -> float | int | None:
    from app.utils.text import normalize_number

    n = normalize_number(value)
    if n is None:
        return None
    return int(n) if float(n).is_integer() else float(n)


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _agg_op(question: str) -> str:
    q = question
    if "平均" in q or "均值" in q:
        return "avg"
    if "最大" in q or "最高" in q or "最多" in q:
        return "max"
    if "最小" in q or "最低" in q or "最少" in q:
        return "min"
    if "记录" in q or "行数" in q or ("条" in q and "多少" in q):
        return "count"
    return "sum"


_OP_LABELS = {"sum": "合计", "avg": "平均值", "max": "最大值", "min": "最小值"}


def _match_column(table: TableRef, question: str) -> int:
    """关键词 → 列匹配：列名命中 +2，示例值命中 +0.5，数值语义引导 +1。"""
    tokens = set(tokenize(question))
    best, best_score = 0, 0.0
    for i, col in enumerate(table.columns):
        score = 2.0 * len(tokens & set(tokenize(col)))
        for row in table.rows[:20]:
            if i < len(row) and str(row[i]).strip():
                vt = set(tokenize(str(row[i])))
                if vt and tokens & vt:
                    score += 0.5
        if any(k in col for k in _NUMERIC_HINT_COLS) and any(k in question for k in _AGG_HINT_WORDS):
            score += 1.0
        if score > best_score:
            best, best_score = i, score
    return best


def _filter_rows(table: TableRef, question: str) -> tuple[list[list[Any]], int | None, str | None]:
    """关键词 → 条件匹配：在列值中找问题关键词，返回 (命中行, 列索引, 关键词)。"""
    tokens = [t for t in tokenize(question) if len(t) >= 2]
    for idx, col in enumerate(table.columns):
        col_tokens = set(tokenize(col))
        for t in tokens:
            if t in col_tokens:
                continue
            hits = [row for row in table.rows if idx < len(row) and t in tokenize(str(row[idx]))]
            if hits:
                return hits, idx, t
    return [], None, None


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def rule_answer(table: TableRef, question: str, intent: str) -> dict[str, Any]:
    """无 Key 规则降级：关键词 → 列/条件匹配 + 内置示例查询，保证可演示。"""
    numeric = [i for i, ty in enumerate(table.types) if ty in ("INTEGER", "REAL")]
    if intent == "aggregate":
        idx = _match_column(table, question)
        op = _agg_op(question)
        if idx in numeric and op != "count":
            col = table.sql_names[idx]
            values = [_num(r[idx]) for r in table.rows if idx < len(r) and _num(r[idx]) is not None]
            if values:
                result = {"sum": sum, "avg": lambda v: sum(v) / len(v), "max": max, "min": min}[op](values)
                sql = f"SELECT {op.upper()}({col}) AS 结果 FROM t"
                answer = (
                    f"「{table.columns[idx]}」{_OP_LABELS[op]}：{_fmt(result)}"
                    f"（共 {len(values)} 条数值记录）"
                )
                return {"sql": sql, "columns": ["结果"], "rows": [[result]], "answer": answer}
        n = len(table.rows)
        sql = "SELECT COUNT(*) AS 记录数 FROM t"
        answer = f"表「{table.name}」共 {n} 条记录"
        return {"sql": sql, "columns": ["记录数"], "rows": [[n]], "answer": answer}

    hits, idx, keyword = _filter_rows(table, question)
    if idx is not None and keyword:
        sql = (
            f"SELECT * FROM t WHERE {table.sql_names[idx]} LIKE '%{_escape_like(keyword)}%' "
            f"LIMIT {MAX_ROWS}"
        )
        answer = f"在「{table.columns[idx]}」列按关键词「{keyword}」匹配到 {len(hits)} 条记录"
    else:
        hits = table.rows[:MAX_ROWS]
        sql = f"SELECT * FROM t LIMIT {MAX_ROWS}"
        answer = f"返回表「{table.name}」前 {len(hits)} 条记录（未识别到筛选条件）"
    return {"sql": sql, "columns": list(table.columns), "rows": hits, "answer": answer}


# ---------------------------------------------------------------- 图表

def _looks_like_date(value: str) -> bool:
    return bool(re.match(r"^\d{4}[-/.]\d{1,2}(?:[-/.]\d{1,2})?$", value)) or "年" in value or "月" in value


def _col_numeric(rows: list[list[Any]], idx: int) -> bool:
    values = [r[idx] for r in rows if idx < len(r) and str(r[idx]).strip()]
    if not values:
        return False
    parsed = [_num(v) for v in values]
    return bool(parsed) and all(v is not None for v in parsed)


def build_chart(columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    """图表数据：首列日期型 → line；存在数值列且行数 ≤ 20 → bar；否则 table。"""
    if not columns:
        return {"type": "table", "columns": [], "rows": []}
    first = str(columns[0])
    date_like = _looks_like_date(first) or (
        bool(rows) and all(_looks_like_date(str(r[0])) for r in rows if r and str(r[0]).strip())
    )
    numeric_cols = [i for i in range(len(columns)) if _col_numeric(rows, i)]
    if date_like and len(rows) > 1:
        ctype = "line"
    elif numeric_cols and len(rows) <= 20:
        ctype = "bar"
    else:
        ctype = "table"
    return {"type": ctype, "columns": columns, "rows": rows[:50]}


# ---------------------------------------------------------------- 入口

def answer_table(table: TableRef, question: str) -> dict[str, Any]:
    """表格问答入口：LLM 链路（自纠错）优先，无 Key/失败时规则降级（source=demo）。"""
    start = time.perf_counter()
    intent = detect_intent(question)
    source = "demo"
    attempts = 0
    tokens = 0
    fallback_reason = ""
    sql = ""
    columns: list[str] = []
    rows: list[list[Any]] = []
    answer = ""

    client = settings_svc.build_llm_client()
    if client.configured:
        try:
            result = generate_with_retry(client, table, question, intent)
            source = "llm"
            attempts = result["attempts"]
            tokens = result["tokens"]
            sql = result["sql"]
            columns = result["columns"]
            rows = result["rows"]
            answer = result["answer"]
        except LLMNotConfigured:
            fallback_reason = "未配置模型 API Key，使用规则降级"
        except LLMError as e:
            fallback_reason = f"模型调用失败：{e}"
        except QaGenerationError as e:
            fallback_reason = f"自纠错后仍失败：{e}"
    else:
        fallback_reason = "未配置模型 API Key，使用规则降级"

    if source == "demo":
        result = rule_answer(table, clean_text(question), intent)
        answer = result["answer"]
        sql = result["sql"]
        columns = result["columns"]
        rows = result["rows"]
        attempts = max(attempts, 1)
        tokens += token_estimate(question) + token_estimate(sql)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "表格问答完成 table=%s intent=%s source=%s elapsed_ms=%s attempts=%s rows=%s",
        table.id, intent, source, elapsed_ms, attempts, len(rows),
    )
    return {
        "answer": answer,
        "sql": sql,
        "columns": columns,
        "rows": rows,
        "chart": build_chart(columns, rows),
        "source": source,
        "metrics": {
            "elapsed_ms": elapsed_ms,
            "attempts": attempts,
            "tokens": tokens,
            "intent": intent,
            "table_id": table.id,
            "table_name": table.name,
            "row_count": len(rows),
            "fallback_reason": fallback_reason,
        },
    }
