"""会话与问答 API 集成测试（M3）：会话 CRUD、SSE 流式、规则降级、LLM mock。"""

from __future__ import annotations

import json

from app.llm.client import LLMError

from tests.conftest import upload_and_wait
from tests.fixtures.documents import make_docx_bytes


def _parsed_doc(client, name: str = "合同.docx") -> dict:
    content = make_docx_bytes(
        [
            (1, "测试合同"),
            (2, "第一条 标的"),
            (None, "甲方出售服务器 10 台，单价 5000 元。"),
            (2, "第二条 付款"),
            (None, "乙方在收货后 30 日内付清全款。"),
        ]
    )
    return upload_and_wait(client, name, content)["document"]


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        ev, data = "message", {}
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
        events.append((ev, data))
    return events


def test_sessions_crud(client):
    r = client.post("/api/sessions", json={"title": "测试会话", "doc_ids": [1]})
    assert r.status_code == 200
    sid = r.json()["id"]
    assert r.json()["doc_ids"] == [1]

    listed = client.get("/api/sessions").json()
    assert any(s["id"] == sid for s in listed)

    detail = client.get(f"/api/sessions/{sid}").json()
    assert detail["session"]["title"] == "测试会话"
    assert detail["messages"] == []

    assert client.delete(f"/api/sessions/{sid}").json()["deleted"] == sid
    assert client.get(f"/api/sessions/{sid}").status_code == 404
    assert client.delete(f"/api/sessions/{sid}").status_code == 404


def test_chat_rule_mode_stream(client):
    doc = _parsed_doc(client)
    r = client.post(
        f"/api/documents/{doc['id']}/chat",
        json={
            "question": "服务器单价是多少？",
            "doc_ids": [doc["id"]],
            "stream": True,
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(r.text)
    kinds = [e[0] for e in events]
    assert kinds[0] == "meta"
    assert "delta" in kinds
    assert kinds[-1] == "done"
    meta = events[0][1]
    done = events[-1][1]
    assert meta["session_id"] > 0
    assert done["source"] == "rule"
    assert done["citations"]
    assert done["citations"][0]["chunk_id"] > 0
    text = "".join(d["text"] for ev, d in events if ev == "delta")
    assert "5000" in text


def test_chat_rule_mode_json(client):
    doc = _parsed_doc(client)
    r = client.post(
        f"/api/documents/{doc['id']}/chat",
        json={
            "question": "付款期限是多久？",
            "doc_ids": [doc["id"]],
            "stream": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "rule"
    assert "30 日" in body["content"]
    assert body["citations"]


def test_chat_auto_session_and_persistence(client):
    doc = _parsed_doc(client)
    r = client.post(
        f"/api/documents/{doc['id']}/chat",
        json={
            "question": "合同金额是多少？",
            "stream": False,
        },
    )
    sid = r.json()["session_id"]
    detail = client.get(f"/api/sessions/{sid}").json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant"]
    assert detail["session"]["doc_ids"] == [doc["id"]]
    assert detail["messages"][0]["content"] == "合同金额是多少？"


def test_chat_requires_parsed_doc(client):
    from app.storage import db

    doc_id = db.create_document(
        name="未解析",
        filename="u.pdf",
        original_name="未解析.pdf",
        ext=".pdf",
        mime="application/pdf",
        size_bytes=10,
        created_at=db.now_iso(),
    )
    r = client.post(
        f"/api/documents/{doc_id}/chat",
        json={
            "question": "你好",
            "doc_ids": [doc_id],
            "stream": False,
        },
    )
    assert r.status_code == 409
    assert (
        client.post(
            "/api/documents/99999/chat",
            json={
                "question": "你好",
                "doc_ids": [99999],
                "stream": False,
            },
        ).status_code
        == 404
    )


def test_chat_empty_question_rejected(client):
    doc = _parsed_doc(client)
    r = client.post(
        f"/api/documents/{doc['id']}/chat",
        json={
            "question": "   ",
            "doc_ids": [doc["id"]],
            "stream": False,
        },
    )
    assert r.status_code == 400


def test_chat_multi_doc(client):
    doc_a = _parsed_doc(client, "甲合同.docx")
    doc_b = _parsed_doc(client, "乙合同.docx")
    r = client.post(
        f"/api/documents/{doc_a['id']}/chat",
        json={
            "question": "服务器单价是多少？",
            "doc_ids": [doc_a["id"], doc_b["id"]],
            "stream": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["citations"]


def test_chat_llm_error_streams_error_event(client, monkeypatch):
    doc = _parsed_doc(client)
    client.put("/api/settings", json={"model": {"api_key": "sk-fake"}})

    def boom(self, messages):
        raise LLMError("网络错误")

    monkeypatch.setattr("app.llm.client.LLMClient.chat_stream", boom)
    r = client.post(
        f"/api/documents/{doc['id']}/chat",
        json={
            "question": "服务器单价是多少？",
            "stream": True,
        },
    )
    events = _parse_sse(r.text)
    assert events[-1][0] == "error"
    assert "网络错误" in events[-1][1]["message"]


def test_chat_llm_json_with_mock(client, monkeypatch):
    doc = _parsed_doc(client)
    client.put("/api/settings", json={"model": {"api_key": "sk-fake"}})

    def fake_chat(self, messages, json_mode=False):
        return "合同金额为 120 万元。"

    monkeypatch.setattr("app.llm.client.LLMClient.chat", fake_chat)
    r = client.post(
        f"/api/documents/{doc['id']}/chat",
        json={
            "question": "合同金额是多少？",
            "stream": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "llm"
    assert "120 万元" in body["content"]
    assert body["citations"]
