# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""语义缓存：对热点/相似问题命中缓存，跳过完整 Agent 链路。

仅缓存通用文档问答(doc_qa)结果，避免缓存与租户/请求强相关的诊断、账单答案。
相似度用 query embedding 余弦比较，阈值见 settings.semantic_cache_sim_threshold。
"""

import json

import numpy as np

from app.cache.redis_client import get_redis
from app.config import settings
from app.llm import client

MAX_ENTRIES = 200


def _key(tenant_id: str) -> str:
    return f"semcache:{tenant_id}"


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


async def get(tenant_id: str, query: str) -> tuple[dict | None, list[float]]:
    """返回 (命中结果或 None, query 向量)。向量回传以便 put 复用，避免重复 embedding。"""
    qv = await client.embed_one(query)
    r = get_redis()
    raw = await r.lrange(_key(tenant_id), 0, -1)
    if not raw:
        return None, qv
    qa = np.array(qv)
    best, best_sim = None, -1.0
    for item in raw:
        e = json.loads(item)
        sim = _cosine(qa, np.array(e["embedding"]))
        if sim > best_sim:
            best_sim, best = sim, e
    if best is not None and best_sim >= settings.semantic_cache_sim_threshold:
        return (
            {
                "answer": best["answer"],
                "citations": best.get("citations", []),
                "card": best.get("card"),
                "intent": best.get("intent"),
                "similarity": round(best_sim, 4),
            },
            qv,
        )
    return None, qv


async def put(tenant_id: str, query: str, result: dict, embedding: list[float]) -> None:
    r = get_redis()
    entry = json.dumps(
        {
            "query": query,
            "embedding": embedding,
            "answer": result["answer"],
            "citations": result.get("citations", []),
            "card": result.get("card"),
            "intent": result.get("intent"),
        },
        ensure_ascii=False,
    )
    await r.lpush(_key(tenant_id), entry)
    # 按租户保留最新 MAX_ENTRIES 条，近似 LRU 防止缓存无限膨胀
    await r.ltrim(_key(tenant_id), 0, MAX_ENTRIES - 1)
