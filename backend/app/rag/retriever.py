# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""混合检索：向量检索 + BM25 关键词检索 → RRF 融合。

错误码类问题支持对 error_code 标量字段精确过滤召回。
"""

import jieba
from rank_bm25 import BM25Okapi

from app.llm import client
from app.rag import store

_bm25: BM25Okapi | None = None
_corpus: list[dict] = []


def _tokenize(text: str) -> list[str]:
    return [t for t in jieba.lcut(text.lower()) if t.strip()]


def _ensure_bm25() -> None:
    """懒加载并缓存 BM25 索引（基于 Milvus 中全部切片）。"""
    global _bm25, _corpus
    if _bm25 is not None:
        return
    _corpus = store.all_chunks()
    if _corpus:
        _bm25 = BM25Okapi([_tokenize(c["content"]) for c in _corpus])


def reset_bm25() -> None:
    """ingest 后调用，强制重建 BM25。"""
    global _bm25, _corpus
    _bm25, _corpus = None, []


def _rrf_fuse(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion：输入多个有序 id 列表，输出融合分。"""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


async def hybrid_search(
    query: str, top_k_each: int = 20, error_code: str | None = None
) -> tuple[list[dict], float]:
    """混合召回，返回 (候选片段, 最高向量余弦)。向量余弦用于更稳健的无命中判定。"""
    _ensure_bm25()

    # 1) 向量检索
    qvec = await client.embed_one(query)
    expr = f'error_code == "{error_code}"' if error_code else None
    vec_hits = store.search(qvec, top_k=top_k_each, expr=expr)
    # 错误码精确过滤若无结果，退回全量向量检索
    if error_code and not vec_hits:
        vec_hits = store.search(qvec, top_k=top_k_each)

    # 2) BM25 关键词检索
    bm25_hits: list[dict] = []
    if _bm25 is not None and _corpus:
        scores = _bm25.get_scores(_tokenize(query))
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k_each]
        bm25_hits = [_corpus[i] for i in top_idx if scores[i] > 0]

    # 用 content 作为去重/融合 key；vec_hits 在前，同片段优先保留向量检索的元信息
    by_content: dict[str, dict] = {}
    for h in vec_hits + bm25_hits:
        by_content.setdefault(h["content"], h)

    vec_order = [h["content"] for h in vec_hits]
    bm25_order = [h["content"] for h in bm25_hits]
    rrf = _rrf_fuse([vec_order, bm25_order])

    candidates = []
    for content, score in sorted(rrf.items(), key=lambda x: x[1], reverse=True):
        item = dict(by_content[content])
        item["rrf_score"] = score
        candidates.append(item)

    top_vec = max((h["score"] for h in vec_hits), default=0.0)
    return candidates, top_vec
