# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""技术支持工作台接口（内部角色）。"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser, require_internal
from app.guardrail import desensitize
from app.llm import client
from app.llm.router import model_for
from app.models import AuditLog, Conversation, Message, Ticket
from app.schemas.chat import TicketUpdateRequest

router = APIRouter(prefix="/api/workbench", tags=["workbench"])

# 工单状态流转
VALID_STATUS = {"new", "processing", "waiting_customer", "resolved", "closed", "escalated"}


@router.get("/tickets")
async def list_tickets(
    tenant_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    error_code: str | None = None,
    category: str | None = None,
    user: CurrentUser = Depends(require_internal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(Ticket).order_by(Ticket.created_at.desc()).limit(100)
    if tenant_id:
        stmt = stmt.where(Ticket.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(Ticket.status == status)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if error_code:
        stmt = stmt.where(Ticket.error_code == error_code)
    if category:
        stmt = stmt.where(Ticket.category == category)
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "tickets": [
            {"ticket_id": t.ticket_id, "tenant_id": t.tenant_id, "title": t.title,
             "category": t.category, "priority": t.priority, "status": t.status,
             "error_code": t.error_code, "assignee": t.assignee,
             "created_at": t.created_at.isoformat()}
            for t in rows
        ]
    }


@router.get("/tickets/{ticket_id}")
async def ticket_with_context(
    ticket_id: str, user: CurrentUser = Depends(require_internal), db: AsyncSession = Depends(get_db)
) -> dict:
    t = (await db.execute(select(Ticket).where(Ticket.ticket_id == ticket_id))).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "工单不存在")
    messages = []
    if t.conversation_id:
        msgs = (
            await db.execute(
                select(Message).where(Message.conversation_id == t.conversation_id).order_by(Message.created_at)
            )
        ).scalars().all()
        messages = [{"role": m.role, "content": m.content, "meta": m.meta} for m in msgs]
    return {
        "ticket": {
            "ticket_id": t.ticket_id, "tenant_id": t.tenant_id, "title": t.title,
            "category": t.category, "priority": t.priority, "status": t.status,
            "summary": t.summary, "ai_diagnosis": t.ai_diagnosis, "evidence": t.evidence,
            "related_request_ids": t.related_request_ids, "error_code": t.error_code,
            "assignee": t.assignee, "conversation_id": t.conversation_id,
        },
        "conversation_messages": messages,
    }


@router.post("/tickets/{ticket_id}")
async def update_ticket(
    ticket_id: str,
    body: TicketUpdateRequest,
    user: CurrentUser = Depends(require_internal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    t = (await db.execute(select(Ticket).where(Ticket.ticket_id == ticket_id))).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "工单不存在")
    if body.status:
        if body.status not in VALID_STATUS:
            raise HTTPException(400, f"非法状态: {body.status}")
        t.status = body.status
    if body.assignee is not None:
        t.assignee = body.assignee
    t.updated_at = datetime.utcnow()
    # 审计
    db.add(AuditLog(tenant_id=t.tenant_id, user_id=user.user_id, action="update_ticket",
                    detail=f"ticket={ticket_id} status={body.status} assignee={body.assignee} note={body.note}"))
    await db.commit()
    return {"ok": True, "ticket_id": ticket_id, "status": t.status, "assignee": t.assignee}


async def _conv_messages(db, conv_id):
    return (
        await db.execute(
            select(Message).where(Message.conversation_id == conv_id).order_by(Message.created_at)
        )
    ).scalars().all()


@router.get("/conversations/{conv_id}/suggest_reply")
async def suggest_reply(
    conv_id: str, user: CurrentUser = Depends(require_internal), db: AsyncSession = Depends(get_db)
) -> dict:
    """基于会话上下文生成 AI 推荐回复话术，供人工编辑后发送。"""
    conv = (await db.execute(select(Conversation).where(Conversation.id == conv_id))).scalar_one_or_none()
    if conv is None:
        raise HTTPException(404, "会话不存在")
    msgs = await _conv_messages(db, conv_id)
    # 仅取最近 8 条作为话术生成上下文，控制 token 并聚焦近期诉求
    convo = "\n".join(f"{'客户' if m.role == 'user' else '助手'}: {m.content}" for m in msgs[-8:])
    gen = await client.chat(
        [
            {"role": "system", "content": "你是资深技术支持。基于会话上下文，为客服起草一段专业、礼貌、可直接发送给客户的回复话术，给出明确结论与下一步。只输出话术正文。"},
            {"role": "user", "content": convo or "（暂无对话内容）"},
        ],
        model=model_for("summarize"), temperature=0.3,
    )
    return {"suggestion": desensitize.desensitize_text(gen.content.strip())}


@router.post("/conversations/{conv_id}/reply")
async def human_reply(
    conv_id: str,
    content: str = Body(..., embed=True),
    user: CurrentUser = Depends(require_internal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """人工回复客户：写入会话（客户可在会话历史看到），并脱敏。"""
    conv = (await db.execute(select(Conversation).where(Conversation.id == conv_id))).scalar_one_or_none()
    if conv is None:
        raise HTTPException(404, "会话不存在")
    msg = Message(
        id="msg_" + uuid.uuid4().hex[:12], conversation_id=conv_id, role="assistant",
        content=desensitize.desensitize_text(content),
        meta={"by": "human", "agent_id": user.user_id, "agent_name": user.display_name},
    )
    db.add(msg)
    conv.transferred_to_human = True
    db.add(AuditLog(tenant_id=conv.tenant_id, user_id=user.user_id, action="human_reply",
                    detail=f"conversation={conv_id}"))
    await db.commit()
    return {"ok": True, "message_id": msg.id}


@router.post("/conversations/{conv_id}/takeover")
async def takeover_conversation(
    conv_id: str, user: CurrentUser = Depends(require_internal), db: AsyncSession = Depends(get_db)
) -> dict:
    conv = (await db.execute(select(Conversation).where(Conversation.id == conv_id))).scalar_one_or_none()
    if conv is None:
        raise HTTPException(404, "会话不存在")
    conv.transferred_to_human = True
    db.add(AuditLog(tenant_id=conv.tenant_id, user_id=user.user_id, action="takeover",
                    detail=f"conversation={conv_id}"))
    await db.commit()
    return {"ok": True, "conversation_id": conv_id, "assignee": user.user_id}
