"""pytest 全局夹具：临时数据目录 + 清库测试客户端。"""
from __future__ import annotations

import os
import tempfile

os.environ["DOCMIND_DATA_DIR"] = tempfile.mkdtemp(prefix="docmind-test-")
os.environ["DOCMIND_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seed import ensure_seed_schemas
from app.storage import db


@pytest.fixture()
def client():
    with TestClient(app) as c:
        db.wipe_data()
        ensure_seed_schemas()
        yield c


@pytest.fixture()
def seed_doc(client) -> dict:
    """上传一个最小 PDF 并完成解析（M2 后使用）。"""
    raise NotImplementedError("M2 提供")
