"""SQLite 存储层：连接管理、建表、数据访问（DAO）。

设计约定：
- 每次操作使用独立连接（WAL 模式），简单可靠、无连接池状态问题。
- 时间统一存 ISO 8601 字符串（本地时间）。
- JSON 字段以 TEXT 存储，读写时编解码。
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable

from app.config import DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  filename TEXT NOT NULL,
  original_name TEXT NOT NULL,
  ext TEXT NOT NULL,
  mime TEXT,
  size_bytes INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'uploaded',
  parse_error TEXT,
  page_count INTEGER,
  char_count INTEGER,
  chunk_count INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  kind TEXT NOT NULL DEFAULT 'text',
  section_path TEXT,
  title TEXT,
  content TEXT NOT NULL,
  page INTEGER,
  char_count INTEGER,
  token_estimate INTEGER,
  image_path TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id, seq);

CREATE TABLE IF NOT EXISTS schemas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  fields_json TEXT NOT NULL,
  is_builtin INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extractions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  schema_id INTEGER NOT NULL REFERENCES schemas(id),
  status TEXT NOT NULL DEFAULT 'draft',
  data_json TEXT,
  confidence_json TEXT,
  field_status_json TEXT,
  citations_json TEXT,
  source TEXT NOT NULL DEFAULT 'llm',
  llm_raw TEXT,
  error TEXT,
  confirmed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_extractions_doc ON extractions(doc_id);

CREATE TABLE IF NOT EXISTS samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  extraction_id INTEGER REFERENCES extractions(id) ON DELETE SET NULL,
  doc_id INTEGER NOT NULL,
  schema_id INTEGER NOT NULL,
  field_key TEXT NOT NULL,
  model_value TEXT,
  human_value TEXT NOT NULL,
  citation TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  doc_ids TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  citations_json TEXT,
  source TEXT DEFAULT 'llm',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS compares (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_a_id INTEGER NOT NULL,
  doc_b_id INTEGER NOT NULL,
  schema_id INTEGER NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  progress INTEGER NOT NULL DEFAULT 0,
  message TEXT,
  payload_json TEXT,
  result_json TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL
);
"""


def jdumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def jloads(raw: str | None, default: Any = None) -> Any:
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def get_conn() -> Iterable[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA_SQL)


def wipe_data() -> None:
    """清空全部业务数据（保留表结构）。测试与设置页使用。"""
    tables = (
        "messages", "sessions", "samples", "extractions", "chunks",
        "documents", "compares", "tasks", "schemas", "settings",
    )
    with get_conn() as conn:
        for t in tables:
            conn.execute(f"DELETE FROM {t}")


# ---------------------------------------------------------------- documents

def create_document(name: str, filename: str, original_name: str, ext: str,
                    mime: str | None, size_bytes: int, created_at: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO documents(name, filename, original_name, ext, mime,
               size_bytes, status, created_at, updated_at)
               VALUES(?,?,?,?,?,?,'uploaded',?,?)""",
            (name, filename, original_name, ext, mime, size_bytes, created_at, created_at),
        )
        return int(cur.lastrowid)


def get_document(doc_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()


def list_documents(query: str = "", status: str = "", ext: str = "",
                   page: int = 1, page_size: int = 20) -> tuple[list[sqlite3.Row], int]:
    where = "WHERE 1=1"
    params: list[Any] = []
    if query:
        where += " AND (name LIKE ? OR original_name LIKE ?)"
        params += [f"%{query}%", f"%{query}%"]
    if status:
        where += " AND status = ?"
        params.append(status)
    if ext:
        where += " AND ext = ?"
        params.append(ext.lower())
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM documents {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM documents {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size],
        ).fetchall()
        return list(rows), int(total)


def update_document(doc_id: int, **fields: Any) -> None:
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [now_iso()]
    with get_conn() as conn:
        conn.execute(f"UPDATE documents SET {keys}, updated_at=? WHERE id=?", vals + [doc_id])


def delete_document(doc_id: int) -> None:
    with get_conn() as conn:
        # 会话引用了该文档的也一并删除
        sessions = conn.execute("SELECT id, doc_ids FROM sessions").fetchall()
        for s in sessions:
            ids = jloads(s["doc_ids"], [])
            if doc_id in ids:
                conn.execute("DELETE FROM messages WHERE session_id=?", (s["id"],))
                conn.execute("DELETE FROM sessions WHERE id=?", (s["id"],))
        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))


# ---------------------------------------------------------------- chunks

def insert_chunks(chunks: list[dict[str, Any]]) -> None:
    with get_conn() as conn:
        conn.executemany(
            """INSERT INTO chunks(doc_id, seq, kind, section_path, title, content,
               page, char_count, token_estimate, image_path, created_at)
               VALUES(:doc_id,:seq,:kind,:section_path,:title,:content,:page,
               :char_count,:token_estimate,:image_path,:created_at)""",
            chunks,
        )


def list_chunks(doc_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return list(conn.execute("SELECT * FROM chunks WHERE doc_id=? ORDER BY seq", (doc_id,)))


def get_chunk(chunk_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone()


def delete_chunks(doc_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))


def count_chunks(doc_id: int) -> int:
    with get_conn() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id=?", (doc_id,)).fetchone()[0])


# ---------------------------------------------------------------- schemas

def list_schemas() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return list(conn.execute("SELECT * FROM schemas ORDER BY is_builtin DESC, id"))


def get_schema(schema_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM schemas WHERE id=?", (schema_id,)).fetchone()


def get_schema_by_key(key: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM schemas WHERE key=?", (key,)).fetchone()


def create_schema(key: str, name: str, description: str, fields: list[dict[str, Any]],
                  is_builtin: bool = False) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO schemas(key, name, description, fields_json, is_builtin, created_at) VALUES(?,?,?,?,?,?)",
            (key, name, description, jdumps(fields), 1 if is_builtin else 0, now_iso()),
        )
        return int(cur.lastrowid)


def update_schema(schema_id: int, name: str, description: str, fields: list[dict[str, Any]]) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE schemas SET name=?, description=?, fields_json=? WHERE id=?",
            (name, description, jdumps(fields), schema_id),
        )


def delete_schema(schema_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM schemas WHERE id=?", (schema_id,))


def count_extractions_for_schema(schema_id: int) -> int:
    with get_conn() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM extractions WHERE schema_id=?", (schema_id,)).fetchone()[0])


# ---------------------------------------------------------------- extractions

def create_extraction(doc_id: int, schema_id: int, source: str = "llm") -> int:
    ts = now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO extractions(doc_id, schema_id, status, source, created_at, updated_at)
               VALUES(?,?,'draft',?,?,?)""",
            (doc_id, schema_id, source, ts, ts),
        )
        return int(cur.lastrowid)


def get_extraction(extraction_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM extractions WHERE id=?", (extraction_id,)).fetchone()


def list_extractions(doc_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return list(conn.execute(
            "SELECT * FROM extractions WHERE doc_id=? ORDER BY id DESC", (doc_id,)))


def update_extraction(extraction_id: int, **fields: Any) -> None:
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [now_iso()]
    with get_conn() as conn:
        conn.execute(f"UPDATE extractions SET {keys}, updated_at=? WHERE id=?", vals + [extraction_id])


def delete_extractions(doc_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM extractions WHERE doc_id=?", (doc_id,))


# ---------------------------------------------------------------- samples

def insert_samples(samples: list[dict[str, Any]]) -> None:
    with get_conn() as conn:
        conn.executemany(
            """INSERT INTO samples(extraction_id, doc_id, schema_id, field_key,
               model_value, human_value, citation, created_at)
               VALUES(:extraction_id,:doc_id,:schema_id,:field_key,:model_value,
               :human_value,:citation,:created_at)""",
            samples,
        )


def list_samples(query: str = "", schema_id: int | None = None,
                 page: int = 1, page_size: int = 50) -> tuple[list[sqlite3.Row], int]:
    select = ("SELECT s.*, d.original_name AS doc_name, sc.name AS schema_name "
              "FROM samples s LEFT JOIN documents d ON s.doc_id=d.id "
              "LEFT JOIN schemas sc ON s.schema_id=sc.id")
    where = "WHERE 1=1"
    params: list[Any] = []
    if query:
        where += " AND (s.field_key LIKE ? OR s.human_value LIKE ? OR s.model_value LIKE ?)"
        params += [f"%{query}%"] * 3
    if schema_id:
        where += " AND s.schema_id = ?"
        params.append(schema_id)
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM samples s {where}", params).fetchone()[0]
        rows = conn.execute(
            f"{select} {where} ORDER BY s.id DESC LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size],
        ).fetchall()
        return list(rows), int(total)


def delete_sample(sample_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM samples WHERE id=?", (sample_id,))


def delete_samples(doc_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM samples WHERE doc_id=?", (doc_id,))


# ---------------------------------------------------------------- sessions / messages

def create_session(title: str, doc_ids: list[int]) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sessions(title, doc_ids, created_at) VALUES(?,?,?)",
            (title, jdumps(doc_ids), now_iso()),
        )
        return int(cur.lastrowid)


def list_sessions() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return list(conn.execute("SELECT * FROM sessions ORDER BY id DESC"))


def get_session(session_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()


def delete_session(session_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))


def create_message(session_id: int, role: str, content: str,
                   citations: list[dict[str, Any]] | None = None, source: str = "llm") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO messages(session_id, role, content, citations_json, source, created_at) VALUES(?,?,?,?,?,?)",
            (session_id, role, content, jdumps(citations or []), source, now_iso()),
        )
        return int(cur.lastrowid)


def list_messages(session_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return list(conn.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY id", (session_id,)))


# ---------------------------------------------------------------- compares

def create_compare(doc_a_id: int, doc_b_id: int, schema_id: int, result: dict[str, Any]) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO compares(doc_a_id, doc_b_id, schema_id, result_json, created_at) VALUES(?,?,?,?,?)",
            (doc_a_id, doc_b_id, schema_id, jdumps(result), now_iso()),
        )
        return int(cur.lastrowid)


def get_compare(compare_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM compares WHERE id=?", (compare_id,)).fetchone()


# ---------------------------------------------------------------- tasks

def create_task(kind: str, payload: dict[str, Any] | None = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tasks(kind, status, progress, message, payload_json, created_at) VALUES(?,'pending',0,'',?,?)",
            (kind, jdumps(payload or {}), now_iso()),
        )
        return int(cur.lastrowid)


def update_task(task_id: int, **fields: Any) -> None:
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE tasks SET {keys} WHERE id=?", list(fields.values()) + [task_id])


def get_task(task_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()


def list_tasks(kind: str = "", limit: int = 50) -> list[sqlite3.Row]:
    sql = "SELECT * FROM tasks"
    params: list[Any] = []
    if kind:
        sql += " WHERE kind = ?"
        params.append(kind)
    with get_conn() as conn:
        return list(conn.execute(sql + " ORDER BY id DESC LIMIT ?", params + [limit]))


def fail_stale_tasks() -> None:
    """服务启动时把遗留 running/pending 任务标记为失败。"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE tasks SET status='failed', error='服务重启，任务中断', finished_at=? WHERE status IN ('pending','running')",
            (now_iso(),),
        )


# ---------------------------------------------------------------- settings

def get_setting(key: str, default: Any = None) -> Any:
    with get_conn() as conn:
        row = conn.execute("SELECT value_json FROM settings WHERE key=?", (key,)).fetchone()
        return jloads(row["value_json"], default) if row else default


def set_setting(key: str, value: Any) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings(key, value_json) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
            (key, jdumps(value)),
        )


def get_all_settings() -> dict[str, Any]:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value_json FROM settings").fetchall()
        return {r["key"]: jloads(r["value_json"]) for r in rows}


def now_iso() -> str:
    from app.models import now_iso as _now
    return _now()

