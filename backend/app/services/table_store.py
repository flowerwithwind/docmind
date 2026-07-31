"""表格存储服务（B2）：把表格块/Excel/内联结构注册为可查询的内存表，并提供只读 SQL 执行。

设计约定：
- 表存于内存注册表（单进程），sqlite3 :memory: 仅用于查询执行；
- 列统一映射为 c1..cN 安全标识符，原始列名仅作展示；
- 所有查询走白名单校验 + PRAGMA query_only + 超时 + 强制 LIMIT。
"""
from __future__ import annotations

import re
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any

from app.models import now_iso
from app.utils.logging import get_logger
from app.utils.text import clean_text, normalize_date, normalize_number

logger = get_logger("table_store")

MAX_ROWS = 100  # 单次查询强制行数上限（LLM 生成的 SQL 未带 LIMIT 时自动追加）
MAX_COLUMNS = 50
MAX_TABLE_ROWS = 2000  # 注册表的最大行数（演示/防御）
QUERY_TIMEOUT_SECONDS = 3.0

_COMMENT_MARKERS = ("--", "/*", "#")
DANGER_KEYWORDS = (
    "ALTER", "ATTACH", "BEGIN", "COMMIT", "CREATE", "DELETE", "DETACH",
    "DROP", "EXEC", "EXECUTE", "EXPLAIN", "GRANT", "INSERT", "MERGE",
    "PRAGMA", "REINDEX", "RELEASE", "REPLACE", "ROLLBACK", "SAVEPOINT",
    "TRUNCATE", "UPDATE", "VACUUM", "WITH",
)

class TableError(RuntimeError):
    """表格业务错误，status_code 供 API 层映射 HTTP 状态。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code

class TableNotFound(TableError):
    pass

class SqlValidationError(TableError):
    pass

class SqlExecutionError(TableError):
    pass

def validate_sql(sql: str) -> str:
    """SQL 白名单校验：仅允许单条只读 SELECT，禁止注释/多语句/危险关键字。"""
    if not isinstance(sql, str) or not sql.strip():
        raise SqlValidationError("SQL 不能为空")
    s = sql.strip()
    for marker in _COMMENT_MARKERS:
        if marker in s:
            raise SqlValidationError(f"禁止 SQL 注释（{marker}）")
    body = s[:-1].rstrip() if s.endswith(";") else s
    if ";" in body:
        raise SqlValidationError("禁止多语句 SQL（仅允许单条 SELECT）")
    upper = body.upper()
    if not re.match(r"^\s*SELECT\b", upper):
        raise SqlValidationError("仅允许只读 SELECT 查询")
    if re.search(r"\bINTO\b", upper):
        raise SqlValidationError("禁止 SELECT INTO 等写语句")
    for kw in DANGER_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", upper):
            raise SqlValidationError(f"包含危险关键字：{kw}")
    if "sqlite_" in body.lower():
        raise SqlValidationError("禁止访问 SQLite 系统表")
    return body

def ensure_limit(sql: str, max_rows: int = MAX_ROWS) -> str:
    """强制行数上限：已有 LIMIT 时封顶，否则追加 LIMIT。"""
    s = sql.strip()
    suffix = ""
    if s.endswith(";"):
        s = s[:-1].rstrip()
        suffix = ";"
    m = re.search(r"\bLIMIT\s+(\d+)\b", s, re.IGNORECASE)
    if m:
        capped = min(int(m.group(1)), max_rows)
        s = f"{s[:m.start()]}LIMIT {capped}{s[m.end():]}"
    else:
        s = f"{s} LIMIT {max_rows}"
    return s + suffix

@dataclass
class TableRef:
    """注册表条目：原始列/行 + 归一化后的 SQL 名称与类型。"""

    id: str
    name: str
    columns: list[str]
    rows: list[list[Any]]
    types: list[str]
    sql_names: list[str]
    source: str = "inline"
    created_at: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

class TableStore:
    def __init__(self) -> None:
        self._tables: dict[str, TableRef] = {}
        self._lock = threading.Lock()
        self._seq = 0
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tableqa")

    # ------------------------------------------------------------ 注册

    def reset(self) -> None:
        with self._lock:
            self._tables.clear()
            self._seq = 0

    def register(
        self,
        columns: list[Any],
        rows: list[Any],
        name: str = "",
        source: str = "inline",
        table_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> TableRef:
        """注册一张表：列名去重、行宽补齐、类型推断、数值/日期归一化。"""
        if not columns:
            raise TableError("表格必须包含列名")
        if not rows:
            raise TableError("表格必须包含至少一行数据")
        cols: list[str] = []
        for i, c in enumerate(columns):
            cname = clean_text(str(c)) or f"列{i + 1}"
            if cname in cols:
                cname = f"{cname}{i + 1}"
            cols.append(cname)
        if len(cols) > MAX_COLUMNS:
            raise TableError(f"列数超过上限（{MAX_COLUMNS}）")
        width = len(cols)
        data: list[list[Any]] = []
        for r in rows[:MAX_TABLE_ROWS]:
            if not isinstance(r, (list, tuple)):
                continue
            row = [clean_text(str(v)) if v is not None else "" for v in r]
            if not any(row):
                continue
            row = row[:width] + [""] * (width - len(row))
            data.append(row)
        if not data:
            raise TableError("表格没有任何有效数据行")
        types = [self._infer_type([r[i] for r in data]) for i in range(width)]
        coerced = [[self._coerce(types[i], r[i]) for i in range(width)] for r in data]
        sql_names = [f"c{i + 1}" for i in range(width)]
        with self._lock:
            self._seq += 1
            tid = table_id or f"t{self._seq}"
            ref = TableRef(
                id=tid,
                name=clean_text(str(name)) or f"表格{tid}",
                columns=cols,
                rows=coerced,
                types=types,
                sql_names=sql_names,
                source=source,
                created_at=now_iso(),
                meta=dict(meta or {}),
            )
            self._tables[tid] = ref
        logger.info("注册表格 id=%s name=%s rows=%s cols=%s source=%s", tid, ref.name, len(ref.rows), len(cols), source)
        return ref

    def ensure_demo(self) -> TableRef:
        """内置演示销售表（无 Key 可演示表格问答）。"""
        if "demo_sales" in self._tables:
            return self._tables["demo_sales"]
        return self.register(
            columns=["月份", "产品", "销售额", "销量"],
            rows=[
                ["2026-01", "服务器", 1200000, 10],
                ["2026-01", "交换机", 450000, 15],
                ["2026-02", "服务器", 1350000, 12],
                ["2026-02", "交换机", 420000, 14],
                ["2026-03", "服务器", 1480000, 13],
                ["2026-03", "交换机", 510000, 17],
            ],
            name="演示销售表",
            source="demo",
            table_id="demo_sales",
        )

    def get(self, table_id: str) -> TableRef:
        with self._lock:
            ref = self._tables.get(table_id)
        if ref is None:
            raise TableNotFound(f"表格不存在：{table_id}", 404)
        return ref

    def list_tables(self) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._tables.values())
        return [
            {
                "id": t.id,
                "name": t.name,
                "columns": t.columns,
                "row_count": len(t.rows),
                "source": t.source,
                "created_at": t.created_at,
            }
            for t in items
        ]

    # ------------------------------------------------------------ 查询

    def query(self, table: TableRef, sql: str) -> tuple[list[str], list[list[Any]]]:
        """校验 → 强制 LIMIT → sqlite 只读执行（超时保护），返回 (columns, rows)。"""
        sql = validate_sql(sql)
        sql = ensure_limit(sql, MAX_ROWS)
        try:
            # 连接在工作线程内创建，避免跨线程使用 SQLite 对象
            future = self._executor.submit(_run_query, table, sql)
            columns, rows = future.result(timeout=QUERY_TIMEOUT_SECONDS)
        except FutureTimeoutError as e:
            raise SqlExecutionError(f"查询执行超时（超过 {QUERY_TIMEOUT_SECONDS}s）") from e
        except sqlite3.Error as e:
            raise SqlExecutionError(f"SQL 执行失败：{e}") from e
        except Exception as e:
            raise SqlExecutionError(f"SQL 执行失败：{e}") from e
        sql_to_orig = dict(zip(table.sql_names, table.columns))
        return [sql_to_orig.get(c, c) for c in columns], rows

    # ------------------------------------------------------------ 类型归一

    def _infer_type(self, values: list[Any]) -> str:
        nonempty = [v for v in values if str(v).strip()]
        if not nonempty:
            return "TEXT"
        if all(normalize_date(v) is not None for v in nonempty):
            return "TEXT"  # 日期按 ISO 文本存储（沿用项目 normalize_date 约定）
        nums = [normalize_number(v) for v in nonempty]
        if all(n is not None for n in nums):
            return "INTEGER" if all(float(n).is_integer() for n in nums) else "REAL"
        return "TEXT"

    def _coerce(self, ty: str, value: Any) -> Any:
        if ty in ("INTEGER", "REAL"):
            n = normalize_number(value)
            if n is None:
                return None
            return int(n) if ty == "INTEGER" else float(n)
        if ty == "TEXT":
            date = normalize_date(value)
            if date is not None:
                return date
        return clean_text(str(value)) if value is not None else ""

def _build_conn(table: TableRef) -> sqlite3.Connection:
    """按注册表内容构建只读内存表（在工作线程内调用，保证连接线程亲和）。"""
    conn = sqlite3.connect(":memory:")
    col_defs = ", ".join(f'"{n}" {t}' for n, t in zip(table.sql_names, table.types))
    conn.execute(f'CREATE TABLE "t" ({col_defs})')
    placeholders = ", ".join(["?"] * len(table.sql_names))
    conn.executemany(f'INSERT INTO "t" VALUES ({placeholders})', [tuple(r) for r in table.rows])
    conn.execute("PRAGMA query_only = ON")  # 纵深防御：数据装载完成后禁止写
    return conn


def _run_query(table: TableRef, sql: str) -> tuple[list[str], list[list[Any]]]:
    conn = _build_conn(table)
    try:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description or []]
        rows = [list(r) for r in cur.fetchall()]
        return columns, rows
    finally:
        conn.close()

table_store = TableStore()
