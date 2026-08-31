# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""会话记忆（Redis）：历史消息窗口 + 已收集实体。

实体记忆让多轮对话中无需重复追问（如已提供的 request_id 后续复用）。
"""

import json

from app.cache.redis_client import get_redis

HISTORY_MAX = 20        # 历史消息窗口
ENTITY_TTL = 60 * 60 * 6  # 实体记忆 6 小时


def _hist_key(conv_id: str) -> str:
    return f"mem:hist:{conv_id}"


def _ent_key(conv_id: str) -> str:
    return f"mem:ent:{conv_id}"


async def append_message(conv_id: str, role: str, content: str) -> None:
    r = get_redis()
    await r.rpush(_hist_key(conv_id), json.dumps({"role": role, "content": content}, ensure_ascii=False))
    await r.ltrim(_hist_key(conv_id), -HISTORY_MAX, -1)
    await r.expire(_hist_key(conv_id), ENTITY_TTL)


async def get_history(conv_id: str) -> list[dict]:
    r = get_redis()
    items = await r.lrange(_hist_key(conv_id), 0, -1)
    return [json.loads(x) for x in items]


async def get_entities(conv_id: str) -> dict:
    r = get_redis()
    raw = await r.get(_ent_key(conv_id))
    return json.loads(raw) if raw else {}


async def update_entities(conv_id: str, new_entities: dict) -> dict:
    """合并新抽取到的非空实体到记忆，返回合并后的实体。"""
    current = await get_entities(conv_id)
    for k, v in (new_entities or {}).items():
        if v not in (None, "", [], {}):
            current[k] = v
    r = get_redis()
    await r.set(_ent_key(conv_id), json.dumps(current, ensure_ascii=False), ex=ENTITY_TTL)
    return current
