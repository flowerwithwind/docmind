"""设置服务：默认值合并、持久化、能力探测、客户端构建。"""
from __future__ import annotations

from typing import Any

from app.config import (
    DEFAULT_API_KEY,
    DEFAULT_BASE_URL,
    DEFAULT_CONTEXT_LIMIT,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_RRF_K,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_K,
)
from app.llm.client import LLMClient, LLMError
from app.storage import db

MODEL_KEY = "model"
RETRIEVAL_KEY = "retrieval"

_DEFAULT_MODEL = {
    "base_url": DEFAULT_BASE_URL,
    "api_key": DEFAULT_API_KEY,
    "model": DEFAULT_MODEL,
    "temperature": DEFAULT_TEMPERATURE,
    "max_tokens": DEFAULT_MAX_TOKENS,
    "embedding_model": DEFAULT_EMBEDDING_MODEL,
}

_DEFAULT_RETRIEVAL = {
    "top_k": DEFAULT_TOP_K,
    "rrf_k": DEFAULT_RRF_K,
    "context_limit": DEFAULT_CONTEXT_LIMIT,
    "dense_enabled": False,
}


def get_model_settings() -> dict[str, Any]:
    return {**_DEFAULT_MODEL, **db.get_setting(MODEL_KEY, {})}


def get_retrieval_settings() -> dict[str, Any]:
    return {**_DEFAULT_RETRIEVAL, **db.get_setting(RETRIEVAL_KEY, {})}


def save_model_settings(data: dict[str, Any]) -> dict[str, Any]:
    cur = get_model_settings()
    allowed = {k: v for k, v in data.items() if k in cur}
    cur.update(allowed)
    db.set_setting(MODEL_KEY, cur)
    return cur


def save_retrieval_settings(data: dict[str, Any]) -> dict[str, Any]:
    cur = get_retrieval_settings()
    allowed = {k: v for k, v in data.items() if k in cur}
    cur.update(allowed)
    db.set_setting(RETRIEVAL_KEY, cur)
    return cur


def build_llm_client() -> LLMClient:
    m = get_model_settings()
    return LLMClient(
        base_url=m["base_url"], api_key=m["api_key"], model=m["model"],
        temperature=float(m["temperature"]), max_tokens=int(m["max_tokens"]),
    )


def get_capabilities() -> dict[str, bool]:
    """探测各能力是否可用（用于前端降级提示）。"""
    m = get_model_settings()
    r = get_retrieval_settings()
    llm_ok = bool(m.get("api_key"))
    ocr_ok = _ocr_available()
    dense_ok = bool(r.get("dense_enabled")) and bool(m.get("api_key"))
    return {"llm": llm_ok, "ocr": ocr_ok, "embedding": dense_ok}


def _ocr_available() -> bool:
    try:
        import paddleocr  # noqa: F401
        return True
    except ImportError:
        return False


def test_connection(data: dict[str, Any]) -> dict[str, Any]:
    """用给定配置（或当前配置）测试模型连接。"""
    cur = get_model_settings()
    cur.update({k: v for k, v in data.items() if k in cur})
    client = LLMClient(
        base_url=cur["base_url"], api_key=cur["api_key"], model=cur["model"],
        temperature=float(cur["temperature"]), max_tokens=int(cur["max_tokens"]),
    )
    err = client.test()
    return {"ok": not err, "error": err}
