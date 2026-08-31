# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""智能对话接口（SSE 流式）。

流程：落库会话/用户消息 → 运行多 Agent 编排 → 落库助手消息 → SSE 流式返回答案 + 元信息。
"""

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agents import supervisor
from app.db import get_db
from app.deps import CurrentUser, get_current_user
from app.models import Conversation, Message
from app.schemas.chat import ChatRequest

router = APIRouter(prefix="/api", tags=["chat"])


def _gen(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


async def _get_or_create_conversation(
    db: AsyncSession, conv_id: str | None, user: CurrentUser
) -> Conversation:
    if conv_id:
        conv = (
            await db.execute(select(Conversation).where(Conversation.id == conv_id))
        ).scalar_one_or_none()
        # 复用已有会话前校验租户归属，防止越权访问他人会话
        if conv and (user.is_internal or conv.tenant_id == user.tenant_id):
            return conv
    conv = Conversation(id=_gen("conv"), tenant_id=user.tenant_id, user_id=user.user_id,
                        channel="web", status="active")
    db.add(conv)
    await db.commit()
    return conv


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await _get_or_create_conversation(db, body.conversation_id, user)

    # 人工模式：会话已转人工 → 客户消息不再走 AI，仅追加并提示等待人工
    if conv.transferred_to_human and not user.is_internal:
        cust_msg = Message(id=_gen("msg"), conversation_id=conv.id, role="user", content=body.message)
        db.add(cust_msg)
        await db.commit()
        ack = "您的消息已转达人工技术支持，我们会尽快回复，可在「我的会话」查看进展。"

        async def human_stream():
            yield {"event": "meta", "data": json.dumps(
                {"conversation_id": conv.id, "message_id": cust_msg.id, "intent": "human", "trace_id": None},
                ensure_ascii=False)}
            for i in range(0, len(ack), 12):
                yield {"event": "token", "data": ack[i:i + 12]}
                await asyncio.sleep(0.02)
            yield {"event": "done", "data": json.dumps({"human_mode": True}, ensure_ascii=False)}

        return EventSourceResponse(human_stream())

    # 落库用户消息
    user_msg = Message(id=_gen("msg"), conversation_id=conv.id, role="user", content=body.message)
    db.add(user_msg)
    await db.commit()

    # 运行编排
    result = await supervisor.run(
        query=body.message, tenant_id=conv.tenant_id, user_id=user.user_id,
        conversation_id=conv.id, is_internal=user.is_internal,
    )

    # 落库助手消息（含诊断元信息）
    assistant_msg = Message(
        id=_gen("msg"), conversation_id=conv.id, role="assistant",
        content=result["answer"],
        meta={
            "intent": result.get("intent"),
            "citations": result.get("citations", []),
            "card": result.get("card"),
            "trace_id": result.get("trace_id"),
            "ticket_id": result.get("ticket_id"),
            "need_human": result.get("need_human"),
            "from_cache": result.get("from_cache", False),
        },
    )
    db.add(assistant_msg)
    # 更新会话状态
    conv.latest_intent = result.get("intent")
    if result.get("need_human"):
        conv.transferred_to_human = True
    await db.commit()

    async def event_stream():
        # 先发会话/消息元信息
        yield {"event": "meta", "data": json.dumps(
            {"conversation_id": conv.id, "message_id": assistant_msg.id,
             "intent": result.get("intent"), "trace_id": result.get("trace_id")},
            ensure_ascii=False)}
        # 流式发送答案（按字符块模拟打字机）
        answer = result["answer"]
        chunk = 18
        for i in range(0, len(answer), chunk):
            yield {"event": "token", "data": answer[i:i + chunk]}
            await asyncio.sleep(0.02)
        # 末尾发完整结构化信息
        yield {"event": "done", "data": json.dumps(
            {
                "answer": answer,
                "card": result.get("card"),
                "citations": result.get("citations", []),
                "ticket_id": result.get("ticket_id"),
                "need_human": result.get("need_human", False),
                "need_clarify": result.get("need_clarify", False),
                "from_cache": result.get("from_cache", False),
                "trace_id": result.get("trace_id"),
            }, ensure_ascii=False)}

    return EventSourceResponse(event_stream())
