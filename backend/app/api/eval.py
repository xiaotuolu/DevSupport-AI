# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""评估与运营指标接口（内部角色）。"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser, require_internal
from app.models import Conversation, Ticket
from app.observability import cost

router = APIRouter(prefix="/api", tags=["eval"])


@router.get("/metrics")
async def metrics(
    user: CurrentUser = Depends(require_internal), db: AsyncSession = Depends(get_db)
) -> dict:
    total_conv = await db.scalar(select(func.count()).select_from(Conversation)) or 0
    resolved = await db.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.resolved_by_ai.is_(True))
    ) or 0
    transferred = await db.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.transferred_to_human.is_(True))
    ) or 0

    intent_rows = (
        await db.execute(
            select(Conversation.latest_intent, func.count()).group_by(Conversation.latest_intent)
        )
    ).all()
    status_rows = (
        await db.execute(select(Ticket.status, func.count()).group_by(Ticket.status))
    ).all()
    priority_rows = (
        await db.execute(select(Ticket.priority, func.count()).group_by(Ticket.priority))
    ).all()

    return {
        "conversations": {
            "total": int(total_conv),
            "resolved_by_ai": int(resolved),
            "transferred_to_human": int(transferred),
            "ai_resolution_rate": round(resolved / total_conv, 3) if total_conv else 0.0,
        },
        "intent_distribution": {(k or "unknown"): int(v) for k, v in intent_rows},
        "tickets": {
            "by_status": {(k or "unknown"): int(v) for k, v in status_rows},
            "by_priority": {(k or "unknown"): int(v) for k, v in priority_rows},
        },
        "token_cost_by_tenant": await cost.summary_by_tenant(),
    }


@router.post("/eval/run")
async def run_eval(user: CurrentUser = Depends(require_internal)) -> dict:
    """运行标准评估集，返回各项指标与 Badcase（耗时较长）。"""
    from eval.run_eval import evaluate

    return await evaluate()
