"""检索服务单元测试（M3）：BM25、稀疏向量、RRF、索引管理。"""

from __future__ import annotations

from app.services.retrieval import (
    INDEX,
    BM25Index,
    Hit,
    RetrievalManager,
    SparseIndex,
    _stable_hash,
)
from app.storage import db


def _seed_chunks(chunks: list[dict]) -> int:
    """直接写入一个文档及其块（跳过上传解析）。"""
    doc_id = db.create_document(
        name="检索测试",
        filename="x.pdf",
        original_name="检索测试.pdf",
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
                "page": 1,
                "char_count": len(c["content"]),
                "token_estimate": 10,
                "image_path": None,
                "created_at": db.now_iso(),
            }
        )
    db.insert_chunks(rows)
    return doc_id


def test_bm25_ranks_relevant_first():
    idx = BM25Index()
    idx.add(1, "合同金额为一百二十万元，预付款百分之三十。")
    idx.add(2, "今天天气很好，适合户外运动。")
    hits = idx.search("合同金额是多少")
    assert hits and hits[0].chunk_id == 1
    assert hits[0].score > 0


def test_bm25_empty_query_and_docs():
    idx = BM25Index()
    assert idx.search("") == []
    idx.add(1, "正文内容")
    assert idx.search("不存在的词zzz") == []


def test_sparse_cosine_similarity():
    idx = SparseIndex()
    idx.add(1, "违约金比例为每日千分之五。")
    idx.add(2, "财务报告显示营业收入增长。")
    hits = idx.search("违约金比例")
    assert hits and hits[0].chunk_id == 1
    assert 0 < hits[0].score <= 1.0


def test_stable_hash_deterministic():
    assert _stable_hash("合同") == _stable_hash("合同")
    assert _stable_hash("合同") != _stable_hash("金额")


def test_rrf_fusion_merges_rankings():
    lists = [
        [Hit(1, 1.0), Hit(2, 0.9)],
        [Hit(3, 1.0), Hit(1, 0.8)],
    ]
    fused = RetrievalManager._rrf(lists, rrf_k=60)
    ids = [h.chunk_id for h in fused]
    assert ids[0] == 1  # 两路都出现 → 融合分最高
    assert set(ids) == {1, 2, 3}


def test_manager_search_from_db(client):
    doc_id = _seed_chunks(
        [
            {"content": "甲方出售服务器十台，单价五千元。", "section": "第一条 标的"},
            {"content": "乙方在收货后三十日内付清全款。", "section": "第二条 付款"},
        ]
    )
    INDEX.reset()
    hits = INDEX.search([doc_id], "服务器单价")
    assert hits
    top = hits[0]
    assert top["doc_id"] == doc_id
    assert "服务器" in top["content"]
    assert "_score" in top and top["_score"] > 0


def test_manager_search_across_docs(client):
    d1 = _seed_chunks([{"content": "合同金额一百二十万元。"}])
    d2 = _seed_chunks([{"content": "营业收入八千五百万元。"}])
    INDEX.reset()
    hits = INDEX.search([d1, d2], "合同金额")
    assert hits
    assert hits[0]["doc_id"] == d1


def test_manager_drop_and_missing_doc(client):
    doc_id = _seed_chunks([{"content": "内容一。"}])
    INDEX.reset()
    assert INDEX.ensure(doc_id) is not None
    db.delete_document(doc_id)
    assert INDEX.ensure(doc_id) is None
    assert INDEX.search([doc_id], "内容") == []


def test_dense_enabled_without_key_falls_back(client):
    doc_id = _seed_chunks([{"content": "毛利率百分之三十二。"}])
    INDEX.reset()
    hits = INDEX.search([doc_id], "毛利率", dense=True)
    assert hits  # 无 Key 时静默降级，仍有结果
