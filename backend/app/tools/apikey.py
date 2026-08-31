# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""API Key 状态查询工具（真实查询 MySQL）。"""

from datetime import datetime

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models import ApiKey
from app.tools.registry import ToolContext, ToolSpec, register


async def query_apikey_status(args: dict, ctx: ToolContext) -> dict:
    """查询 API Key 状态。支持按 api_key_id 或 app_id 查询。"""
    api_key_id = args.get("api_key_id")
    app_id = args.get("app_id")
    async with AsyncSessionLocal() as s:
        stmt = select(ApiKey)
        if api_key_id:
            stmt = stmt.where(ApiKey.id == api_key_id)
        elif app_id:
            stmt = stmt.where(ApiKey.app_id == app_id)
        else:
            return {"found": False, "reason": "需提供 api_key_id 或 app_id"}
        keys = (await s.execute(stmt)).scalars().all()
        # 租户隔离：客户侧只能看到本租户的 Key
        keys = [k for k in keys if ctx.is_internal or k.tenant_id == ctx.tenant_id]
        if not keys:
            return {"found": False, "reason": "未找到对应 API Key 或无权访问"}
        now = datetime(2026, 6, 15)  # 固定为演示数据基准时间，保证过期判定可复现
        return {
            "found": True,
            "keys": [
                {
                    "api_key_masked": k.key_masked,
                    "status": k.status,
                    "expire_at": k.expire_at.isoformat() if k.expire_at else None,
                    "expired": bool(k.expire_at and k.expire_at < now),
                }
                for k in keys
            ],
        }


register(ToolSpec(
    name="query_apikey_status",
    description="查询应用 API Key 的状态（有效/过期/禁用）与过期时间。用于诊断 401 鉴权失败。",
    parameters={
        "type": "object",
        "properties": {
            "app_id": {"type": "string", "description": "应用 ID，如 app_acme"},
            "api_key_id": {"type": "string", "description": "API Key ID（可选）"},
        },
    },
    func=query_apikey_status,
    category="apikey",
))
