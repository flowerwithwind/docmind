"""Schema API 测试。"""
from __future__ import annotations


def _schema_payload(key="my_schema", fields=None):
    return {
        "key": key,
        "name": "我的 Schema",
        "description": "测试",
        "fields": fields if fields is not None else [
            {"key": "name", "label": "名称", "type": "string", "required": True},
            {"key": "amount", "label": "金额", "type": "number", "required": False},
        ],
    }


def test_list_schemas_has_builtins(client):
    r = client.get("/api/schemas")
    assert r.status_code == 200
    schemas = r.json()
    keys = {s["key"] for s in schemas}
    assert {"contract", "financial"} <= keys
    builtin = next(s for s in schemas if s["key"] == "contract")
    assert builtin["is_builtin"] is True
    assert len(builtin["fields"]) >= 10


def test_create_and_get_schema(client):
    r = client.post("/api/schemas", json=_schema_payload())
    assert r.status_code == 201
    sid = r.json()["id"]
    got = client.get(f"/api/schemas/{sid}")
    assert got.status_code == 200
    assert got.json()["key"] == "my_schema"
    assert got.json()["is_builtin"] is False


def test_create_duplicate_key_409(client):
    client.post("/api/schemas", json=_schema_payload(key="dup"))
    r = client.post("/api/schemas", json=_schema_payload(key="dup"))
    assert r.status_code == 409


def test_create_invalid_key_422(client):
    r = client.post("/api/schemas", json=_schema_payload(key="Bad Key!"))
    assert r.status_code == 422


def test_create_empty_fields_422(client):
    r = client.post("/api/schemas", json=_schema_payload(fields=[]))
    assert r.status_code == 422


def test_update_builtin_forbidden(client):
    schemas = client.get("/api/schemas").json()
    bid = next(s["id"] for s in schemas if s["key"] == "contract")
    r = client.put(f"/api/schemas/{bid}", json=_schema_payload())
    assert r.status_code == 403


def test_update_custom_ok(client):
    sid = client.post("/api/schemas", json=_schema_payload()).json()["id"]
    r = client.put(f"/api/schemas/{sid}", json=_schema_payload(key="my_schema", fields=[
        {"key": "name", "label": "名称", "type": "string", "required": True},
    ]))
    assert r.status_code == 200
    assert len(r.json()["fields"]) == 1


def test_delete_custom_ok(client):
    sid = client.post("/api/schemas", json=_schema_payload()).json()["id"]
    r = client.delete(f"/api/schemas/{sid}")
    assert r.status_code == 204
    assert client.get(f"/api/schemas/{sid}").status_code == 404


def test_delete_builtin_forbidden(client):
    schemas = client.get("/api/schemas").json()
    bid = next(s["id"] for s in schemas if s["key"] == "financial")
    assert client.delete(f"/api/schemas/{bid}").status_code == 403


def test_get_missing_404(client):
    assert client.get("/api/schemas/99999").status_code == 404
