"""解析服务单元测试（FR-01/FR-02）。"""
from __future__ import annotations

import pytest

from app.services.parser import OcrUnavailable, ParseError, parse_document
from tests.fixtures.documents import (
    make_docx_bytes,
    make_docx_with_table_bytes,
    make_mini_pdf_bytes,
    make_xlsx_bytes,
)


def _save(tmp_path, name, content) -> str:
    p = tmp_path / name
    p.write_bytes(content)
    return str(p)


def test_parse_docx_headings_and_text(tmp_path):
    content = make_docx_bytes([
        (1, "第一章"),
        (None, "正文第一段。"),
        (2, "1.1 小节"),
        (None, "正文第二段。"),
    ])
    result = parse_document(_save(tmp_path, "a.docx", content), ".docx")
    assert result["page_count"] == 1
    blocks = result["pages"][0]["blocks"]
    levels = [b.get("heading_level") for b in blocks if b["kind"] == "text"]
    assert 1 in levels and 2 in levels
    assert result["char_count"] > 10


def test_parse_docx_table(tmp_path):
    content = make_docx_with_table_bytes()
    result = parse_document(_save(tmp_path, "t.docx", content), ".docx")
    tables = [b for p in result["pages"] for b in p["blocks"] if b["kind"] == "table"]
    assert len(tables) == 1
    assert "服务器" in tables[0]["table"]
    assert "|" in tables[0]["table"]


def test_parse_xlsx(tmp_path):
    content = make_xlsx_bytes([["品名", "数量"], ["服务器", "10"]])
    result = parse_document(_save(tmp_path, "d.xlsx", content), ".xlsx")
    tables = [b for p in result["pages"] for b in p["blocks"] if b["kind"] == "table"]
    assert len(tables) == 1
    assert "服务器" in tables[0]["table"]


def test_parse_pdf(tmp_path):
    content = make_mini_pdf_bytes(["Hello DocMind", "This is a PDF line."])
    result = parse_document(_save(tmp_path, "p.pdf", content), ".pdf")
    assert result["page_count"] == 1
    text = " ".join(b.get("text", "") for p in result["pages"] for b in p["blocks"])
    assert "DocMind" in text


def test_parse_unsupported_ext(tmp_path):
    with pytest.raises(ParseError):
        parse_document(_save(tmp_path, "a.txt", b"hello"), ".txt")


def test_parse_image_without_ocr_raises(tmp_path):
    # 测试环境未安装 paddleocr → 应抛出 OcrUnavailable（用户可读提示）
    with pytest.raises(OcrUnavailable):
        parse_document(_save(tmp_path, "s.png", b"\x89PNG\r\n"), ".png")
