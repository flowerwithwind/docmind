"""导出服务（FR-06）：抽取结果 JSON / Excel / Markdown 三种格式。"""

from __future__ import annotations

import io
import json
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.storage import db


def _display(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _md_escape(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def build_export(row, fmt: str) -> tuple[bytes, str, str]:
    """构建导出文件，返回 (内容字节, media_type, 文件名)。"""
    schema = db.get_schema(row["schema_id"])
    fields = {
        f["key"]: f for f in (db.jloads(schema["fields_json"], []) if schema else [])
    }
    data = db.jloads(row["data_json"], {})
    confidence = db.jloads(row["confidence_json"], {})
    field_status = db.jloads(row["field_status_json"], {})
    citations = db.jloads(row["citations_json"], {})

    rows: list[dict[str, Any]] = []
    for key, value in data.items():
        field = fields.get(key, {})
        cites = citations.get(key) or []
        snippets = [
            str(c.get("snippet") or "")
            for c in cites
            if isinstance(c, dict) and c.get("snippet")
        ]
        rows.append(
            {
                "key": key,
                "label": field.get("label") or key,
                "value": _display(value),
                "confidence": confidence.get(key),
                "status": field_status.get(key, ""),
                "citation": "；".join(snippets)[:300],
            }
        )

    ext_id = row["id"]
    schema_name = schema["name"] if schema else ""
    if fmt == "json":
        payload = {
            "id": ext_id,
            "doc_id": row["doc_id"],
            "schema_id": row["schema_id"],
            "schema_name": schema_name,
            "status": row["status"],
            "source": row["source"],
            "confirmed_at": row["confirmed_at"],
            "created_at": row["created_at"],
            "rows": rows,
            "data": data,
            "confidence": confidence,
            "field_status": field_status,
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return content, "application/json; charset=utf-8", f"extraction-{ext_id}.json"

    if fmt == "excel":
        wb = Workbook()
        ws = wb.active
        ws.title = "抽取结果"
        header = ["字段", "标签", "值", "置信度", "状态", "依据"]
        ws.append(header)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for r in rows:
            ws.append(
                [
                    r["key"], r["label"], r["value"],
                    r["confidence"], r["status"], r["citation"],
                ]
            )
        for i, width in enumerate((20, 20, 40, 12, 12, 60), start=1):
            ws.column_dimensions[get_column_letter(i)].width = width
        buf = io.BytesIO()
        wb.save(buf)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return buf.getvalue(), media, f"extraction-{ext_id}.xlsx"

    # markdown
    lines = [
        f"# 抽取结果 #{ext_id}",
        "",
        f"- 文档 ID：{row['doc_id']}",
        f"- Schema：{schema_name}",
        f"- 状态：{row['status']}（来源：{row['source']}）",
        f"- 确认时间：{row['confirmed_at'] or '-'}",
        "",
        "| 字段 | 标签 | 值 | 置信度 | 状态 | 依据 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {_md_escape(r['key'])} | {_md_escape(r['label'])} | "
            f"{_md_escape(r['value'])} | {r['confidence']} | {r['status']} | "
            f"{_md_escape(r['citation'])} |"
        )
    content = ("\n".join(lines) + "\n").encode("utf-8")
    return content, "text/markdown; charset=utf-8", f"extraction-{ext_id}.md"