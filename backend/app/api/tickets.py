# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""工单查询接口（客户侧：我的工单）+ 反馈接口。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import uuid
from datetime import datetime

from sqlalchemy import desc

from app.db import get_db
from app.deps import CurrentUser, assert_tenant_access, get_current_user
from app.models import Conversation, Feedback, Message, Ticket
from app.schemas.chat import FeedbackRequest

router = APIRouter(prefix="/api", tags=["tickets"])


@router.get("/tickets")
async def my_tickets(
    user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    stmt = select(Ticket).order_by(Ticket.created_at.desc()).limit(50)
    if not user.is_internal:
        stmt = stmt.where(Ticket.tenant_id == user.tenant_id)
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "tickets": [
            {"ticket_id": t.ticket_id, "title": t.title, "category": t.category,
             "priority": t.priority, "status": t.status, "error_code": t.error_code,
             "created_at": t.created_at.isoformat()}
            for t in rows
        ]
    }


@router.get("/tickets/{ticket_id}")
async def ticket_detail(
    ticket_id: str, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    t = (await db.execute(select(Ticket).where(Ticket.ticket_id == ticket_id))).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "工单不存在")
    assert_tenant_access(user, t.tenant_id)
    return {
        "ticket_id": t.ticket_id, "title": t.title, "category": t.category, "priority": t.priority,
        "status": t.status, "summary": t.summary, "related_request_ids": t.related_request_ids,
        "related_endpoint": t.related_endpoint, "error_code": t.error_code,
        "ai_diagnosis": t.ai_diagnosis, "evidence": t.evidence, "assignee": t.assignee,
        "conversation_id": t.conversation_id, "created_at": t.created_at.isoformat(),
    }


@router.post("/feedback")
async def submit_feedback(
    body: FeedbackRequest, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    conv = (
        await db.execute(select(Conversation).where(Conversation.id == body.conversation_id))
    ).scalar_one_or_none()
    if conv is None:
        raise HTTPException(404, "会话不存在")
    assert_tenant_access(user, conv.tenant_id)
    db.add(Feedback(conversation_id=body.conversation_id, message_id=body.message_id,
                    tenant_id=conv.tenant_id, type=body.type))
    # 反馈分三类：resolved/unresolved 记满意度，need_human 触发转人工建单
    if body.type in ("resolved", "unresolved"):
        conv.satisfaction = body.type
        conv.resolved_by_ai = body.type == "resolved"

    ticket_id = None
    if body.type == "need_human":
        conv.transferred_to_human = True
        # 一键转人工：真实创建工单，附最近一条用户问题作为上下文
        last_user = (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == conv.id, Message.role == "user")
                .order_by(desc(Message.created_at))
            )
        ).scalars().first()
        title = (last_user.content[:60] if last_user else "用户请求人工支持")
        ticket_id = "tk_" + datetime(2026, 6, 15).strftime("%Y%m%d") + "_" + uuid.uuid4().hex[:6]
        db.add(Ticket(
            ticket_id=ticket_id, tenant_id=conv.tenant_id, user_id=user.user_id,
            category="人工支持", priority="P2", status="new", title=title,
            summary=title, ai_diagnosis="用户在会话中主动请求人工支持",
            conversation_id=conv.id,
        ))
    await db.commit()
    return {"ok": True, "ticket_id": ticket_id}
