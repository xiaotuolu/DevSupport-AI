# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""套餐 / 用量 / 账单查询工具（真实查询 MySQL）。"""

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models import Invoice, Plan, Tenant, UsageRecord
from app.tools.registry import ToolContext, ToolSpec, register


async def query_plan(args: dict, ctx: ToolContext) -> dict:
    """查询租户当前套餐（QPS、月配额、单价）。"""
    async with AsyncSessionLocal() as s:
        tenant = (
            await s.execute(select(Tenant).where(Tenant.id == ctx.tenant_id))
        ).scalar_one_or_none()
        if tenant is None or tenant.plan_id is None:
            return {"found": False, "reason": "未找到套餐信息"}
        plan = (await s.execute(select(Plan).where(Plan.id == tenant.plan_id))).scalar_one()
        return {
            "found": True,
            "plan_name": plan.name,
            "qps_limit": plan.qps_limit,
            "monthly_quota": plan.monthly_quota,
            "price_per_call": plan.price_per_call,
            "overage_price_per_call": plan.overage_price_per_call,
        }


async def query_usage(args: dict, ctx: ToolContext) -> dict:
    """查询某月调用量与超额量。"""
    month = args.get("month")
    async with AsyncSessionLocal() as s:
        stmt = select(UsageRecord).where(UsageRecord.tenant_id == ctx.tenant_id)
        if month:
            stmt = stmt.where(UsageRecord.month == month)
        stmt = stmt.order_by(UsageRecord.month)
        rows = (await s.execute(stmt)).scalars().all()
        if not rows:
            return {"found": False, "reason": "未找到用量记录"}
        return {
            "found": True,
            "usage": [
                {"month": r.month, "call_count": r.call_count, "overage_count": r.overage_count}
                for r in rows
            ],
        }


async def query_bill(args: dict, ctx: ToolContext) -> dict:
    """查询某月账单及费用构成。"""
    month = args.get("month")
    async with AsyncSessionLocal() as s:
        stmt = select(Invoice).where(Invoice.tenant_id == ctx.tenant_id)
        if month:
            stmt = stmt.where(Invoice.month == month)
        stmt = stmt.order_by(Invoice.month)
        rows = (await s.execute(stmt)).scalars().all()
        if not rows:
            return {"found": False, "reason": "未找到账单"}
        return {
            "found": True,
            "bills": [
                {"month": r.month, "amount": r.amount, "status": r.status, "items": r.items}
                for r in rows
            ],
        }


register(ToolSpec(
    name="query_plan",
    description="查询当前租户的套餐信息：套餐名、QPS 上限、月调用量配额、单价与超额单价。",
    parameters={"type": "object", "properties": {}},
    func=query_plan,
    category="billing",
))
register(ToolSpec(
    name="query_usage",
    description="查询租户某月（YYYY-MM）的调用量与超额量；不传 month 则返回全部月份。",
    parameters={
        "type": "object",
        "properties": {"month": {"type": "string", "description": "月份，如 2026-06"}},
    },
    func=query_usage,
    category="billing",
))
register(ToolSpec(
    name="query_bill",
    description="查询租户某月账单金额与费用构成（基础费用、超额费用）。",
    parameters={
        "type": "object",
        "properties": {"month": {"type": "string", "description": "月份，如 2026-06"}},
    },
    func=query_bill,
    category="billing",
))
