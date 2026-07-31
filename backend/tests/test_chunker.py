"""分块与结构树单元测试（FR-03）。"""
from __future__ import annotations

from app.services.chunker import attach_chunk_ids, build_chunks, build_tree


def _pages(blocks_per_page: list[list[dict]]) -> list[dict]:
    return [{"page": i + 1, "blocks": blocks} for i, blocks in enumerate(blocks_per_page)]


LONG_BODY_1 = "这里是正文内容，用于验证分块。它足够长，不会被短块合并逻辑吞掉，保证标题边界得到验证。" * 2
LONG_BODY_2 = "背景段落的内容同样足够长，不会被合并进前一块，从而保留独立的章节路径。" * 2


def test_headings_create_section_path_and_tree():
    pages = _pages([[
        {"kind": "text", "text": "第一章 概述", "heading_level": 1},
        {"kind": "text", "text": LONG_BODY_1, "heading_level": None},
        {"kind": "text", "text": "1.1 背景", "heading_level": 2},
        {"kind": "text", "text": LONG_BODY_2, "heading_level": None},
    ]])
    chunks = build_chunks(pages)
    paths = [c["section_path"] for c in chunks if c["kind"] == "text"]
    assert paths[0] == "第一章 概述"
    assert paths[1] == "第一章 概述 > 1.1 背景"

    tree = build_tree(pages)
    assert tree["title"] == "文档"
    assert tree["children"][0]["title"] == "第一章 概述"
    assert tree["children"][0]["children"][0]["title"] == "1.1 背景"
    attach_chunk_ids(tree, chunks)
    assert tree["children"][0]["children"][0]["chunk_ids"] == [1]


def test_table_and_image_are_own_chunks():
    pages = _pages([[
        {"kind": "text", "text": "数据表", "heading_level": 1},
        {"kind": "text", "text": "本章包含一张数据表和一张配图。", "heading_level": None},
        {"kind": "table", "table": "| a | b |\n|---|---|", "heading_level": None},
        {"kind": "image", "image_path": "doc_x_1.png", "heading_level": None},
    ]])
    chunks = build_chunks(pages)
    kinds = [c["kind"] for c in chunks]
    assert kinds == ["text", "table", "image"]
    assert chunks[1]["content"].startswith("| a |")
    assert chunks[2]["image_path"] == "doc_x_1.png"
    assert chunks[2]["char_count"] == 0


def test_short_chunks_merge_with_next():
    pages = _pages([[
        {"kind": "text", "text": "短句一。", "heading_level": None},
        {"kind": "text", "text": "短句二，与前面合并。", "heading_level": None},
    ]])
    chunks = build_chunks(pages, min_chars=80)
    assert len(chunks) == 1
    assert "短句一" in chunks[0]["content"] and "短句二" in chunks[0]["content"]
    assert chunks[0]["seq"] == 0


def test_long_text_splits_on_sentence_boundary():
    sentences = [f"第{i}句：这是一段用于测试超长文本切分的句子，包含足够多的内容。" for i in range(30)]
    pages = _pages([[{"kind": "text", "text": "".join(sentences), "heading_level": None}]])
    chunks = build_chunks(pages, max_chars=200)
    assert len(chunks) > 1
    assert all(len(c["content"]) <= 210 for c in chunks)
    assert [c["seq"] for c in chunks] == list(range(len(chunks)))


def test_empty_pages_no_chunks():
    assert build_chunks([]) == []


def test_tree_handles_level_skip():
    pages = _pages([[
        {"kind": "text", "text": "一级", "heading_level": 1},
        {"kind": "text", "text": "三级（跳级）", "heading_level": 3},
    ]])
    tree = build_tree(pages)
    assert tree["children"][0]["children"][0]["title"] == "三级（跳级）"
