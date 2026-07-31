"""智能分块 + 结构树构建。

规则（对应需求文档 FR-03）：
1. 标题层级作为切块边界
2. 表格独立成块；图片独立成块（含上下文标题）
3. 长块按句子边界截断（默认 1500 字符）
4. 短块与相邻块合并（默认 <80 字符）
"""
from __future__ import annotations

from typing import Any

from app.config import DEFAULT_CHUNK_MAX_CHARS, DEFAULT_CHUNK_MIN_CHARS
from app.utils.text import split_sentences, token_estimate

SECTION_SEP = " > "


def build_chunks(pages: list[dict[str, Any]], max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
                 min_chars: int = DEFAULT_CHUNK_MIN_CHARS) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    stack: list[tuple[int, str]] = []  # (level, title)
    buf = ""
    buf_page: int | None = None
    seq = 0

    def section_path() -> str:
        return SECTION_SEP.join(t for _, t in stack) if stack else ""

    def flush() -> None:
        nonlocal buf, seq
        text = buf.strip()
        buf = ""
        if not text:
            return
        parts = [text] if len(text) <= max_chars else _split_long(text, max_chars)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            chunks.append({
                "seq": seq, "kind": "text", "section_path": section_path(),
                "title": stack[-1][1] if stack else "",
                "content": part, "page": buf_page,
                "char_count": len(part), "token_estimate": token_estimate(part),
            })
            seq += 1

    def flush_short() -> None:
        """合并过短的相邻正文块（仅当累积缓冲 < min_chars 时延后 flush）。"""
        nonlocal buf
        if buf and len(buf.strip()) < min_chars:
            return  # 保留缓冲，与后续文本合并
        flush()

    for page in pages:
        for block in page.get("blocks", []):
            kind = block["kind"]
            if kind == "table":
                flush()
                table_text = block.get("table", "").strip()
                if table_text:
                    chunks.append({
                        "seq": seq, "kind": "table", "section_path": section_path(),
                        "title": stack[-1][1] if stack else "表格",
                        "content": table_text, "page": page["page"],
                        "char_count": len(table_text), "token_estimate": token_estimate(table_text),
                    })
                    seq += 1
            elif kind == "image":
                flush()
                img_path = block.get("image_path")
                if img_path:
                    chunks.append({
                        "seq": seq, "kind": "image", "section_path": section_path(),
                        "title": stack[-1][1] if stack else "图片",
                        "content": f"[图片：{img_path}]", "page": page["page"],
                        "char_count": 0, "token_estimate": 0, "image_path": img_path,
                    })
                    seq += 1
            else:
                level = block.get("heading_level")
                if level:
                    flush()
                    while stack and stack[-1][0] >= level:
                        stack.pop()
                    stack.append((level, block["text"]))
                else:
                    text = block.get("text", "").strip()
                    if not text:
                        continue
                    if buf and len(buf) + len(text) > max_chars:
                        flush_short()
                    if not buf:
                        buf_page = page["page"]
                    buf += text + "\n"
    flush()

    # 短块合并：把 < min_chars 的 text 块并入下一块
    merged: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    for c in chunks:
        if c["kind"] != "text":
            if pending:
                merged.append(pending)
                pending = None
            merged.append(c)
            continue
        if pending is None and c["char_count"] < min_chars:
            pending = c
            continue
        if pending is not None:
            c = {**c, "content": pending["content"] + "\n" + c["content"],
                 "char_count": pending["char_count"] + c["char_count"],
                 "token_estimate": pending["token_estimate"] + c["token_estimate"]}
            pending = None
        merged.append(c)
    if pending:
        merged.append(pending)
    # 重新编号
    for i, c in enumerate(merged):
        c["seq"] = i
    return merged


def _split_long(text: str, max_chars: int) -> list[str]:
    sentences = split_sentences(text)
    parts: list[str] = []
    buf = ""
    for s in sentences:
        if len(s) > max_chars:  # 超长句直接截断
            if buf:
                parts.append(buf)
                buf = ""
            parts.append(s[:max_chars])
            continue
        if buf and len(buf) + len(s) > max_chars:
            parts.append(buf)
            buf = ""
        buf += s
    if buf:
        parts.append(buf)
    return parts


def build_tree(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """从页流构建结构树（不依赖 chunk id）。"""
    root = {"title": "文档", "level": 0, "page": None, "children": [], "chunk_ids": []}
    stack = [root]
    for page in pages:
        for block in page.get("blocks", []):
            level = block.get("heading_level")
            if level:
                title = block.get("text", "").strip() or "未命名章节"
                node = {"title": title, "level": level, "page": page["page"],
                        "children": [], "chunk_ids": []}
                while stack and stack[-1]["level"] >= level:
                    stack.pop()
                if not stack:
                    stack = [root]
                stack[-1]["children"].append(node)
                stack.append(node)
    return root


def attach_chunk_ids(tree: dict[str, Any], chunks: list[dict[str, Any]]) -> None:
    """按 section_path 把 chunk id 挂到树节点。"""
    def find_node(node: dict, path: str) -> dict | None:
        parts = [p for p in path.split(SECTION_SEP) if p]
        cur = node
        for p in parts:
            nxt = None
            for child in cur["children"]:
                if child["title"] == p:
                    nxt = child
                    break
            if nxt is None:
                return None
            cur = nxt
        return cur

    for c in chunks:
        node = find_node(tree, c.get("section_path") or "")
        if node is not None:
            node["chunk_ids"].append(c["seq"])
