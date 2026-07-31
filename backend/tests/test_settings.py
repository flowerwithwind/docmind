"""设置 API 与任务 API 测试。"""
from __future__ import annotations


def test_settings_defaults(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["model"]["model"]
    assert body["retrieval"]["top_k"] == 6
    assert body["capabilities"]["llm"] is False


def test_settings_update_persists(client):
    r = client.put("/api/settings", json={"model": {"model": "my-model", "temperature": 0.7}})
    assert r.status_code == 200
    assert r.json()["model"]["model"] == "my-model"
    assert r.json()["model"]["temperature"] == 0.7
    again = client.get("/api/settings").json()
    assert again["model"]["model"] == "my-model"


def test_settings_unknown_keys_ignored(client):
    r = client.put("/api/settings", json={"model": {"hacker": True}})
    assert r.status_code == 200
    assert "hacker" not in r.json()["model"]


def test_test_connection_without_key(client):
    r = client.post("/api/settings/test", json={"model": {"api_key": ""}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"]


def test_tasks_empty_and_missing(client):
    assert client.get("/api/tasks").json() == []
    assert client.get("/api/tasks/99999").status_code == 404
