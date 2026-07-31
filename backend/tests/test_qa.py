"""问答编排单元测试（M3）：上下文组装、消息构建、规则问答器、引用。"""

from __future__ import annotations

from app.services import qa
from app.services.retrieval import INDEX
from app.storage import db


def _seed_doc(chunks: list[dict]) -> int:
    doc_id = db.create_document(
        name="问答测试",
        filename="q.pdf",
        original_name="问答测试.pdf",
        ext=".pdf",
        mime="application/pdf",
        size_bytes=100,
        created_at=db.now_iso(),
    )
    rows = []
    for i, c in enumerate(chunks):
        rows.append(
            {
                "doc_id": doc_id,
                "seq": i,
                "kind": "text",
                "section_path": c.get("section", ""),
                "title": c.get("title", ""),
                "content": c["content"],
                "page": 2,
                "char_count": len(c["content"]),
                "token_estimate": 10,
                "image_path": None,
                "created_at": db.now_iso(),
            }
        )
    db.insert_chunks(rows)
    return doc_id


def test_build_context_includes_meta_and_numbering():
    hits = [
        {"id": 1, "page": 3, "section_path": "3.2 付款方式", "content": "预付款 30%"},
        {
            "id": 2,
            "page": 4,
            "section_path": "",
            "title": "4. 违约",
            "content": "违约金 5%",
        },
    ]
    ctx = qa.build_context(hits, context_limit=8000)
    assert "[1]" in ctx and "第3页" in ctx and "3.2 付款方式" in ctx
    assert "[2]" in ctx and "违约金" in ctx


def test_build_context_trims_by_budget():
    hits = [
        {"id": 1, "page": 1, "section_path": "a", "content": "甲" * 300},
        {"id": 2, "page": 1, "section_path": "b", "content": "乙" * 300},
    ]
    ctx = qa.build_context(hits, context_limit=200)
    assert "[2]" not in ctx


def test_build_messages_appends_history_and_question():
    history = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！"},
    ]
    msgs = qa.build_messages("合同金额？", "上下文", history)
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["role"] == "user"
    assert "合同金额？" in msgs[-1]["content"]
    assert any(m["content"] == "你好" for m in msgs)


def test_rule_answer_found(client):
    doc_id = _seed_doc(
        [
            {"content": "合同总金额为人民币一百二十万元。", "section": "第一条 金额"},
        ]
    )
    INDEX.reset()
    text, citations = qa.rule_answer([doc_id], "合同金额是多少")
    assert text and "一百二十万" in text
    assert citations and citations[0].chunk_id > 0
    assert citations[0].page == 2


def test_rule_answer_not_found(client):
    doc_id = _seed_doc([{"content": "合同总金额为人民币一百二十万元。"}])
    INDEX.reset()
    text, citations = qa.rule_answer([doc_id], "完全无关的话题xyz")
    assert text == qa.NO_ANSWER
    assert citations == []


def test_rule_answer_empty_docs(client):
    text, citations = qa.rule_answer([99999], "合同金额")
    assert text == qa.NO_ANSWER
    assert citations == []


def test_citations_of_builds_fields():
    chunks = [{"id": 7, "page": 3, "section_path": "2. 付款", "content": "预付款\n30%"}]
    cites = qa.citations_of(chunks)
    assert cites[0].chunk_id == 7
    assert cites[0].section == "2. 付款"
    assert "\n" not in cites[0].snippet


def test_chunk_text_streams_pieces():
    text = "未在文档中找到相关信息" * 5
    pieces = list(qa.chunk_text(text, size=10))
    assert "".join(pieces) == text
    assert len(pieces) > 1
