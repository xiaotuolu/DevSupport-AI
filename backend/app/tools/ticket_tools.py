# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""工单工具（真实写入 MySQL）+ 高风险操作占位（AI 不可直接执行）。"""

import uuid
from datetime import datetime

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models import Ticket
from app.tools.registry import ToolContext, ToolSpec, register


async def create_ticket(args: dict, ctx: ToolContext) -> dict:
    """创建技术支持工单（含 AI 诊断摘要与证据）。"""
    ticket_id = "tk_" + datetime(2026, 6, 15).strftime("%Y%m%d") + "_" + uuid.uuid4().hex[:6]
    async with AsyncSessionLocal() as s:
        s.add(
            Ticket(
                ticket_id=ticket_id,
                tenant_id=ctx.tenant_id,
                user_id=args.get("user_id", ""),
                category=args.get("category", "其它"),
                priority=args.get("priority", "P2"),
                status="new",
                title=args.get("title", "技术支持工单"),
                summary=args.get("summary", ""),
                related_request_ids=args.get("related_request_ids", []),
                related_endpoint=args.get("related_endpoint"),
                error_code=args.get("error_code"),
                evidence=args.get("evidence", ""),
                ai_diagnosis=args.get("ai_diagnosis", ""),
                conversation_id=args.get("conversation_id"),
            )
        )
        await s.commit()
    return {"ticket_id": ticket_id, "status": "new", "priority": args.get("priority", "P2")}


async def query_ticket(args: dict, ctx: ToolContext) -> dict:
    """按 ticket_id 查询工单状态。"""
    ticket_id = args.get("ticket_id")
    async with AsyncSessionLocal() as s:
        t = (
            await s.execute(select(Ticket).where(Ticket.ticket_id == ticket_id))
        ).scalar_one_or_none()
        if t is None:
            return {"found": False}
        if not ctx.is_internal and t.tenant_id != ctx.tenant_id:
            return {"found": False, "reason": "无权访问"}
        return {"found": True, "ticket_id": t.ticket_id, "status": t.status,
                "priority": t.priority, "title": t.title}


async def _high_risk_blocked(args: dict, ctx: ToolContext) -> dict:
    return {"blocked": True, "reason": "高风险操作必须由人工或后台审批执行"}


register(ToolSpec(
    name="create_ticket",
    description="当问题无法自助解决、需人工介入或用户要求人工时，创建技术支持工单，附带 AI 诊断摘要与证据。",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "category": {"type": "string", "description": "如 API报错/套餐账单/数据质量/故障投诉"},
            "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
            "summary": {"type": "string"},
            "related_request_ids": {"type": "array", "items": {"type": "string"}},
            "related_endpoint": {"type": "string"},
            "error_code": {"type": "string"},
            "evidence": {"type": "string"},
            "ai_diagnosis": {"type": "string"},
        },
        "required": ["title", "category", "summary"],
    },
    func=create_ticket,
    category="ticket",
))
register(ToolSpec(
    name="query_ticket",
    description="按 ticket_id 查询工单当前状态与优先级。",
    parameters={"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]},
    func=query_ticket,
    category="ticket",
))

# ---- 高风险工具：注册但标记 high_risk，不暴露给 AI ----
for _name, _desc in [
    ("reset_api_key", "重置 API Key"),
    ("change_plan", "变更套餐"),
    ("refund", "退款/账单调整"),
]:
    register(ToolSpec(
        name=_name, description=_desc, parameters={"type": "object", "properties": {}},
        func=_high_risk_blocked, high_risk=True, category="high_risk",
    ))
