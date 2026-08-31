# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""链路观测接口：查询 AgentTrace 与工具调用日志（供前端链路可视化）。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser, require_internal
from app.models import AgentTrace, Ticket, ToolCallLog

router = APIRouter(prefix="/api/traces", tags=["observability"])


@router.get("/{trace_id}")
async def get_trace(
    trace_id: str,
    user: CurrentUser = Depends(require_internal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    steps = (
        await db.execute(
            select(AgentTrace).where(AgentTrace.trace_id == trace_id).order_by(AgentTrace.step_order)
        )
    ).scalars().all()
    if not steps:
        raise HTTPException(404, "未找到该 trace")
    tools = (
        await db.execute(
            select(ToolCallLog).where(ToolCallLog.trace_id == trace_id).order_by(ToolCallLog.id)
        )
    ).scalars().all()
    return {
        "trace_id": trace_id,
        "conversation_id": steps[0].conversation_id,
        "tenant_id": steps[0].tenant_id,
        "total_duration_ms": sum(s.duration_ms for s in steps),
        "total_tokens": sum(s.token_usage for s in steps),
        "steps": [
            {
                "step_order": s.step_order,
                "agent_name": s.agent_name,
                "status": s.status,
                "duration_ms": s.duration_ms,
                "token_usage": s.token_usage,
                "input_summary": s.input_summary,
                "output_summary": s.output_summary,
                "hit_docs": s.hit_docs,
                "error_message": s.error_message,
            }
            for s in steps
        ],
        "tool_calls": [
            {
                "tool_name": t.tool_name,
                "status": t.status,
                "duration_ms": t.duration_ms,
                "args_summary": t.args_summary,
                "result_summary": t.result_summary,
                "error_message": t.error_message,
            }
            for t in tools
        ],
    }


@router.get("")
async def list_traces(
    conversation_id: str | None = None,
    tenant_id: str | None = None,
    request_id: str | None = None,
    ticket_id: str | None = None,
    limit: int = 20,
    user: CurrentUser = Depends(require_internal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """按会话/租户/request_id/ticket_id 列出最近的 trace（去重 trace_id）。"""
    stmt = select(AgentTrace).order_by(AgentTrace.id.desc())
    if conversation_id:
        stmt = stmt.where(AgentTrace.conversation_id == conversation_id)
    if tenant_id:
        stmt = stmt.where(AgentTrace.tenant_id == tenant_id)
    if request_id:
        # 经工具调用日志反查：哪些 trace 调用过含该 request_id 的工具
        tids = (
            await db.execute(
                select(ToolCallLog.trace_id).where(ToolCallLog.args_summary.like(f"%{request_id}%"))
            )
        ).scalars().all()
        stmt = stmt.where(AgentTrace.trace_id.in_(tids or ["__none__"]))
    if ticket_id:
        # 经工单关联会话反查
        t = (await db.execute(select(Ticket).where(Ticket.ticket_id == ticket_id))).scalar_one_or_none()
        stmt = stmt.where(AgentTrace.conversation_id == (t.conversation_id if t else "__none__"))
    rows = (await db.execute(stmt.limit(limit * 10))).scalars().all()
    seen, traces = set(), []
    for r in rows:
        if r.trace_id in seen:
            continue
        seen.add(r.trace_id)
        traces.append({"trace_id": r.trace_id, "conversation_id": r.conversation_id,
                       "tenant_id": r.tenant_id, "created_at": r.created_at.isoformat()})
        if len(traces) >= limit:
            break
    return {"traces": traces}
