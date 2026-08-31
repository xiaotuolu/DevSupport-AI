# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""会话查询接口。"""

import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import CurrentUser, assert_tenant_access, get_current_user
from app.guardrail import desensitize
from app.models import Conversation, Message

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(
    user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    stmt = select(Conversation).order_by(Conversation.updated_at.desc()).limit(50)
    # 内部支持人员可见全部会话；外部客户仅见本租户下自己的会话
    if not user.is_internal:
        stmt = stmt.where(Conversation.tenant_id == user.tenant_id, Conversation.user_id == user.user_id)
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "conversations": [
            {"id": c.id, "tenant_id": c.tenant_id, "status": c.status,
             "latest_intent": c.latest_intent, "transferred_to_human": c.transferred_to_human,
             "satisfaction": c.satisfaction, "updated_at": c.updated_at.isoformat()}
            for c in rows
        ]
    }


@router.get("/{conv_id}")
async def get_conversation(
    conv_id: str, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    conv = (
        await db.execute(select(Conversation).where(Conversation.id == conv_id))
    ).scalar_one_or_none()
    if conv is None:
        raise HTTPException(404, "会话不存在")
    assert_tenant_access(user, conv.tenant_id)
    msgs = (
        await db.execute(
            select(Message).where(Message.conversation_id == conv_id).order_by(Message.created_at)
        )
    ).scalars().all()
    return {
        "conversation": {"id": conv.id, "tenant_id": conv.tenant_id, "status": conv.status,
                         "latest_intent": conv.latest_intent,
                         "transferred_to_human": conv.transferred_to_human,
                         "satisfaction": conv.satisfaction},
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "meta": m.meta,
             "created_at": m.created_at.isoformat()}
            for m in msgs
        ],
    }


@router.post("/{conv_id}/messages")
async def add_customer_message(
    conv_id: str,
    content: str = Body(..., embed=True),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """客户在人工模式下补充消息（不走 AI），供「我的会话」回话使用。"""
    conv = (
        await db.execute(select(Conversation).where(Conversation.id == conv_id))
    ).scalar_one_or_none()
    if conv is None:
        raise HTTPException(404, "会话不存在")
    assert_tenant_access(user, conv.tenant_id)
    msg = Message(
        id="msg_" + uuid.uuid4().hex[:12], conversation_id=conv_id, role="user",
        content=desensitize.desensitize_text(content),
    )
    db.add(msg)
    await db.commit()
    return {"ok": True, "message_id": msg.id}
