# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""重排序：对混合召回的候选用 gte-rerank-v2 精排，取 top_n。"""

from app.llm import client


async def rerank_candidates(
    query: str, candidates: list[dict], top_n: int = 5
) -> list[dict]:
    """对候选片段精排，返回带 rerank_score 的 top_n（降序）。"""
    if not candidates:
        return []
    docs = [c["content"] for c in candidates]
    results = await client.rerank(query, docs, top_n=top_n)
    reranked = []
    for r in results:
        item = dict(candidates[r["index"]])
        item["rerank_score"] = r["score"]
        reranked.append(item)
    return reranked
