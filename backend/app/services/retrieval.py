"""检索服务：BM25 + 稀疏 hash 向量 + RRF 融合（可选稠密）。

对应需求文档 FR-04 / §6.4：
- 每个文档一个 DocIndex：块缓存 + BM25 + 稀疏向量
- RetrievalManager 维护 doc_id -> DocIndex 的内存索引，可从 chunks 表懒加载/重建
- RRF 融合多路检索结果（k 默认 60）
- 稠密检索为可选：配置 dense_enabled 且 Key 可用时对 BM25 候选块做 embedding 重排，
  任何失败都静默降级回稀疏检索
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from app.storage import db
from app.utils.text import tokenize

logger = logging.getLogger("docmind.retrieval")

HASH_DIM = 4096
BM25_K1 = 1.5
BM25_B = 0.75
RULE_MIN_SCORE = 0.15  # 规则问答器命中阈值


def _stable_hash(token: str) -> int:
    """稳定哈希（跨进程一致，保证索引可重建）。"""
    digest = hashlib.md5(token.encode("utf-8")).digest()[:4]
    return int.from_bytes(digest, "big") % HASH_DIM


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


@dataclass
class Hit:
    chunk_id: int
    score: float


class BM25Index:
    """纯 Python BM25（k1=1.5, b=0.75），中文 2-gram + 英文按词。"""

    def __init__(self, k1: float = BM25_K1, b: float = BM25_B) -> None:
        self.k1 = k1
        self.b = b
        self._docs: dict[int, Counter[str]] = {}
        self._doc_lens: dict[int, int] = {}
        self._df: Counter[str] = Counter()
        self._avg_len = 0.0
        self._dirty = True

    def add(self, chunk_id: int, text: str) -> None:
        toks = tokenize(text)
        self._docs[chunk_id] = Counter(toks)
        self._doc_lens[chunk_id] = len(toks)
        self._dirty = True

    def _build(self) -> None:
        if not self._dirty:
            return
        self._df = Counter()
        for toks in self._docs.values():
            for t in set(toks):
                self._df[t] += 1
        n = len(self._docs)
        self._avg_len = sum(self._doc_lens.values()) / n if n else 0.0
        self._dirty = False

    def search(self, query: str, top_k: int = 6) -> list[Hit]:
        self._build()
        q_toks = tokenize(query)
        if not q_toks or not self._docs:
            return []
        n = len(self._docs)
        scores: dict[int, float] = defaultdict(float)
        for t in set(q_toks):
            df = self._df.get(t, 0)
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for cid, toks in self._docs.items():
                tf = toks.get(t, 0)
                if not tf:
                    continue
                dl = self._doc_lens[cid]
                if self._avg_len:
                    denom = tf + self.k1 * (1 - self.b + self.b * dl / self._avg_len)
                else:
                    denom = tf + self.k1
                scores[cid] += idf * (tf * (self.k1 + 1) / denom)
        ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        return [Hit(chunk_id=cid, score=s) for cid, s in ordered]


class SparseIndex:
    """hash(token) % 4096 计数向量 + 余弦相似度（无 Key 时的"稠密"降级）。"""

    def __init__(self, dim: int = HASH_DIM) -> None:
        self.dim = dim
        self._vecs: dict[int, Counter[int]] = {}

    def add(self, chunk_id: int, text: str) -> None:
        vec: Counter[int] = Counter()
        for t in tokenize(text):
            vec[_stable_hash(t)] += 1
        self._vecs[chunk_id] = vec

    def search(self, query: str, top_k: int = 6) -> list[Hit]:
        q = Counter(_stable_hash(t) for t in tokenize(query))
        if not q or not self._vecs:
            return []
        q_norm = math.sqrt(sum(v * v for v in q.values())) or 1.0
        scored: list[tuple[int, float]] = []
        for cid, vec in self._vecs.items():
            inter = sum(cnt * vec.get(h, 0) for h, cnt in q.items())
            if not inter:
                continue
            v_norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            scored.append((cid, inter / (q_norm * v_norm)))
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return [Hit(chunk_id=cid, score=s) for cid, s in scored[:top_k]]


class DocIndex:
    """单文档索引：块缓存 + 两路检索器。"""

    def __init__(self, doc_id: int, chunks: list[dict[str, Any]]) -> None:
        self.doc_id = doc_id
        self.chunks: dict[int, dict[str, Any]] = {c["id"]: c for c in chunks}
        self.bm25 = BM25Index()
        self.sparse = SparseIndex()
        for c in chunks:
            content = c.get("content") or ""
            # 标题与章节路径一并索引，支持按章节名提问命中正文
            index_text = " ".join(
                p for p in (c.get("section_path"), c.get("title"), content) if p
            )
            self.bm25.add(c["id"], index_text)
            self.sparse.add(c["id"], index_text)

    def get(self, chunk_id: int) -> dict[str, Any] | None:
        return self.chunks.get(chunk_id)


class RetrievalManager:
    """内存检索索引管理器：懒加载 + 失效重建。"""

    def __init__(self) -> None:
        self._docs: dict[int, DocIndex] = {}

    def reset(self) -> None:
        self._docs.clear()

    def drop(self, doc_id: int) -> None:
        self._docs.pop(doc_id, None)

    def ensure(self, doc_id: int) -> DocIndex | None:
        # 先校验文档仍存在，避免返回已删除文档的陈旧索引
        if db.get_document(doc_id) is None:
            self.drop(doc_id)
            return None
        idx = self._docs.get(doc_id)
        if idx is not None:
            return idx
        rows = db.list_chunks(doc_id)
        if not rows:
            return None
        idx = DocIndex(doc_id, [dict(r) for r in rows])
        self._docs[doc_id] = idx
        return idx

    def search(
        self,
        doc_ids: list[int],
        query: str,
        top_k: int = 6,
        rrf_k: int = 60,
        dense: bool = False,
    ) -> list[dict[str, Any]]:
        """跨文档检索：BM25 + 稀疏（+ 可选稠密）→ RRF 融合。

        返回带 _score 的块字典列表（按融合分降序）。
        """
        valid: list[int] = []
        chunk_map: dict[int, dict[str, Any]] = {}
        for d in doc_ids:
            idx = self.ensure(d)
            if idx is not None:
                valid.append(d)
                chunk_map.update(idx.chunks)
        if not valid:
            return []
        lists: list[list[Hit]] = []
        raw_scores: dict[int, float] = defaultdict(float)
        for d in valid:
            idx = self._docs[d]
            bm_hits = idx.bm25.search(query, top_k=top_k * 2)
            sp_hits = idx.sparse.search(query, top_k=top_k * 2)
            lists.append(bm_hits)
            lists.append(sp_hits)
            for h in bm_hits:
                raw_scores[h.chunk_id] = max(raw_scores[h.chunk_id], h.score)
            for h in sp_hits:
                raw_scores[h.chunk_id] = max(raw_scores[h.chunk_id], h.score)
        if dense:
            dense_hits = self._dense_search(valid, query, top_k * 2, chunk_map)
            if dense_hits:
                lists.append(dense_hits)
                for h in dense_hits:
                    raw_scores[h.chunk_id] = max(raw_scores[h.chunk_id], h.score)
        fused = self._rrf(lists, rrf_k=rrf_k)[:top_k]
        out: list[dict[str, Any]] = []
        for hit in fused:
            chunk = chunk_map.get(hit.chunk_id)
            if chunk is None:
                continue
            item = dict(chunk)
            item["_score"] = hit.score
            item["_raw"] = raw_scores.get(hit.chunk_id, 0.0)
            out.append(item)
        return out

    @staticmethod
    def _rrf(lists: list[list[Hit]], rrf_k: int = 60) -> list[Hit]:
        scores: dict[int, float] = defaultdict(float)
        for ranked in lists:
            for rank, hit in enumerate(ranked, start=1):
                scores[hit.chunk_id] += 1.0 / (rrf_k + rank)
        ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return [Hit(chunk_id=cid, score=s) for cid, s in ordered]

    def _dense_search(
        self,
        doc_ids: list[int],
        query: str,
        top_k: int,
        chunk_map: dict[int, dict[str, Any]],
    ) -> list[Hit]:
        """可选稠密检索：对 BM25 候选块做 embedding 余弦重排。

        未配置 / 网络失败 / 响应异常都静默降级（返回空列表）。
        """
        try:
            from app.services import settings as settings_svc

            m = settings_svc.get_model_settings()
            if not m.get("api_key"):
                return []
            from app.llm.client import LLMClient

            client = LLMClient(
                base_url=m["base_url"],
                api_key=m["api_key"],
                model=m["model"],
                temperature=0.0,
                max_tokens=8,
            )
            cand_ids: list[int] = []
            for d in doc_ids:
                idx = self._docs.get(d)
                if idx is not None:
                    cand_ids += [
                        h.chunk_id for h in idx.bm25.search(query, top_k=top_k)
                    ]
            cand_ids = list(dict.fromkeys(cand_ids))
            if not cand_ids:
                return []
            texts = [chunk_map[cid]["content"] for cid in cand_ids]
            vecs = client.embed([query] + texts)
            qv = vecs[0]
            scored = [
                Hit(chunk_id=cid, score=_cosine(qv, cv))
                for cid, cv in zip(cand_ids, vecs[1:])
            ]
            scored.sort(key=lambda h: h.score, reverse=True)
            return scored[:top_k]
        except Exception as e:  # noqa: BLE001
            logger.warning("dense retrieval disabled: %s", e)
            return []


# 全局检索索引单例（进程内共享）
INDEX = RetrievalManager()
