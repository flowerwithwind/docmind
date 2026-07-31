"""健康检查与基础信息测试。"""
from __future__ import annotations


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "DocMind"
    assert body["status"] == "ok"
    assert body["storage"] == "ok"
    assert "capabilities" in body


def test_health_capabilities(client):
    body = client.get("/api/health").json()
    caps = body["capabilities"]
    assert set(caps) >= {"llm", "ocr", "embedding"}
    # 测试环境无 Key、无 OCR
    assert caps["llm"] is False
    assert caps["ocr"] is False
