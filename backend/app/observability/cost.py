# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""Token / 成本统计：按会话与租户记录用量。"""

from sqlalchemy import func, select

from app.db import AsyncSessionLocal
from app.models import TokenUsage


async def record(tenant_id: str, conversation_id: str, model: str, total_tokens: int) -> None:
    if total_tokens <= 0:
        return
    async with AsyncSessionLocal() as s:
        s.add(
            TokenUsage(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                model=model,
                total_tokens=total_tokens,
            )
        )
        await s.commit()


async def summary_by_tenant() -> list[dict]:
    """按租户汇总 token 用量（成本看板用）。"""
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(
                select(
                    TokenUsage.tenant_id,
                    func.count().label("turns"),
                    func.sum(TokenUsage.total_tokens).label("tokens"),
                ).group_by(TokenUsage.tenant_id)
            )
        ).all()
        return [
            {"tenant_id": r.tenant_id, "turns": int(r.turns), "total_tokens": int(r.tokens or 0)}
            for r in rows
        ]
