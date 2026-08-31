# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""路由缓存：缓存意图识别结果（intent/route/entities），命中则跳过意图识别 LLM。

仅在无对话历史（首轮）时使用，避免相同 query 在不同上下文下复用错误结果。
"""

import hashlib
import json

from app.cache.redis_client import get_redis

TTL = 60 * 60 * 24


def _key(query: str) -> str:
    norm = query.strip().lower()
    return "routecache:" + hashlib.md5(norm.encode("utf-8")).hexdigest()


async def get(query: str) -> dict | None:
    raw = await get_redis().get(_key(query))
    return json.loads(raw) if raw else None


async def put(query: str, result: dict) -> None:
    payload = {
        "intent": result["intent"],
        "confidence": result["confidence"],
        "entities": result["entities"],
        "route": result["route"],
    }
    await get_redis().set(_key(query), json.dumps(payload, ensure_ascii=False), ex=TTL)
