"""OpenAI 兼容 LLM 客户端（同步实现，兼容 DeepSeek / OpenAI / Ollama）。

- chat / chat_stream：对话补全
- embed：向量化（可选，用于稠密检索）
- 全部网络调用带超时与错误归一化；未配置 Key 时抛出 LLMNotConfigured。
"""
from __future__ import annotations

import json
from typing import Any, Iterator

import httpx

from app.config import (
    DEFAULT_API_KEY,
    DEFAULT_BASE_URL,
    DEFAULT_EMBEDDING_API_KEY,
    DEFAULT_EMBEDDING_BASE_URL,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
)


class LLMError(RuntimeError):
    pass


class LLMNotConfigured(LLMError):
    pass


def _clean_base_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


class LLMClient:
    def __init__(self, base_url: str = "", api_key: str = "", model: str = "",
                 temperature: float = 0.2, max_tokens: int = 4096,
                 timeout: float = 120.0):
        self.base_url = _clean_base_url(base_url or DEFAULT_BASE_URL)
        self.api_key = api_key or DEFAULT_API_KEY
        self.model = model or DEFAULT_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def chat(self, messages: list[dict[str, str]], json_mode: bool = False) -> str:
        if not self.configured:
            raise LLMNotConfigured("未配置模型 API Key（可在设置页配置，或使用演示规则模式）")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=self._headers())
        except httpx.HTTPError as e:
            raise LLMError(f"模型请求失败：{e.__class__.__name__}") from e
        if resp.status_code >= 400:
            # JSON 模式不被支持时降级重试
            if json_mode and resp.status_code in (400, 422):
                payload.pop("response_format", None)
                try:
                    with httpx.Client(timeout=self.timeout) as client:
                        resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=self._headers())
                except httpx.HTTPError as e:
                    raise LLMError(f"模型请求失败：{e.__class__.__name__}") from e
            else:
                raise LLMError(f"模型接口错误 {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f"模型响应格式异常: {resp.text[:300]}") from e

    def chat_stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        """流式对话，逐个产出文本增量。"""
        if not self.configured:
            raise LLMNotConfigured("未配置模型 API Key（可在设置页配置，或使用演示规则模式）")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=self._headers()) as resp:
                    if resp.status_code >= 400:
                        raise LLMError(f"模型接口错误 {resp.status_code}: {resp.read()[:300]}")
                    for line in resp.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0]["delta"].get("content")
                        except (KeyError, IndexError, ValueError):
                            continue
                        if delta:
                            yield delta
        except httpx.HTTPError as e:
            raise LLMError(f"模型请求失败：{e.__class__.__name__}") from e

    def embed(self, texts: list[str]) -> list[list[float]]:
        """调用 OpenAI 兼容 embeddings 接口。"""
        base = _clean_base_url(DEFAULT_EMBEDDING_BASE_URL) or self.base_url
        key = DEFAULT_EMBEDDING_API_KEY or self.api_key
        if not key:
            raise LLMNotConfigured("未配置 Embedding API Key")
        payload = {"model": DEFAULT_EMBEDDING_MODEL, "input": texts}
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"{base}/embeddings", json=payload,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                )
        except httpx.HTTPError as e:
            raise LLMError(f"Embedding 请求失败：{e.__class__.__name__}") from e
        if resp.status_code >= 400:
            raise LLMError(f"Embedding 接口错误 {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
            return [item["embedding"] for item in data["data"]]
        except (KeyError, ValueError) as e:
            raise LLMError(f"Embedding 响应格式异常: {resp.text[:300]}") from e

    def test(self) -> str:
        """返回空字符串表示连接成功，否则返回错误信息。"""
        try:
            out = self.chat([{"role": "user", "content": "ping"}], json_mode=False)
        except LLMError as e:
            return str(e)
        return "" if out else "模型返回为空"
