# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""调用日志查询工具（真实查询 MySQL）。"""

from datetime import timedelta

from sqlalchemy import func, select

from app.db import AsyncSessionLocal
from app.models import ApiCallLog, ApiKey
from app.tools.registry import ToolContext, ToolSpec, register


async def query_call_log(args: dict, ctx: ToolContext) -> dict:
    """按 request_id 查询单次调用日志。"""
    request_id = args.get("request_id")
    if not request_id:
        return {"found": False, "reason": "缺少 request_id"}
    async with AsyncSessionLocal() as s:
        log = (
            await s.execute(select(ApiCallLog).where(ApiCallLog.request_id == request_id))
        ).scalar_one_or_none()
        if log is None:
            return {"found": False, "reason": "未找到该 request_id 的日志"}
        # 租户隔离：客户侧只能查本租户
        if not ctx.is_internal and log.tenant_id != ctx.tenant_id:
            return {"found": False, "reason": "无权访问其它租户的调用日志"}
        key_masked = None
        if log.api_key_id:
            key = (
                await s.execute(select(ApiKey).where(ApiKey.id == log.api_key_id))
            ).scalar_one_or_none()
            key_masked = key.key_masked if key else None
        return {
            "found": True,
            "request_id": log.request_id,
            "app_id": log.app_id,
            "endpoint": log.endpoint,
            "http_status": log.http_status,
            "error_code": log.error_code,
            "latency_ms": log.latency_ms,
            "api_key_masked": key_masked,
            "called_at": log.created_at.isoformat(),
        }


async def query_recent_call_stats(args: dict, ctx: ToolContext) -> dict:
    """统计近 N 分钟某接口的调用情况（用于 429 限流诊断）。"""
    endpoint = args.get("endpoint")
    minutes = int(args.get("minutes", 240))
    async with AsyncSessionLocal() as s:
        # 锚点：优先定位该租户(+接口)最近一次 429 限流事件的时间；无 429 则用最近一条日志。
        # 这样能围绕"限流事件"统计窗口，不依赖系统当前时间，也不被随机背景日志漂移。
        base_conds = [ApiCallLog.tenant_id == ctx.tenant_id]
        if endpoint:
            base_conds.append(ApiCallLog.endpoint == endpoint)
        anchor = (
            await s.execute(
                select(func.max(ApiCallLog.created_at)).where(
                    *base_conds, ApiCallLog.http_status == 429
                )
            )
        ).scalar()
        if anchor is None:
            anchor = (
                await s.execute(select(func.max(ApiCallLog.created_at)).where(*base_conds))
            ).scalar()
        if anchor is None:
            return {"total": 0, "by_status": {}}
        since = anchor - timedelta(minutes=minutes)
        conds = [ApiCallLog.tenant_id == ctx.tenant_id, ApiCallLog.created_at >= since]
        if endpoint:
            conds.append(ApiCallLog.endpoint == endpoint)
        rows = (
            await s.execute(
                select(ApiCallLog.http_status, func.count())
                .where(*conds)
                .group_by(ApiCallLog.http_status)
            )
        ).all()
        by_status = {int(st): int(cnt) for st, cnt in rows}
        total = sum(by_status.values())
        n429 = by_status.get(429, 0)
        return {
            "endpoint": endpoint,
            "window_minutes": minutes,
            "total": total,
            "by_status": by_status,
            "rate_limited_count": n429,
            "rate_limited_ratio": round(n429 / total, 3) if total else 0.0,
        }


register(ToolSpec(
    name="query_call_log",
    description="根据 request_id 查询某次 API 调用的状态码、错误码、耗时、调用时间等日志详情。",
    parameters={
        "type": "object",
        "properties": {"request_id": {"type": "string", "description": "调用请求 ID，如 req_20260615_8842"}},
        "required": ["request_id"],
    },
    func=query_call_log,
    category="logs",
))

register(ToolSpec(
    name="query_recent_call_stats",
    description="统计某接口近 N 分钟的调用量与各状态码分布，用于判断是否触发限流(429)。",
    parameters={
        "type": "object",
        "properties": {
            "endpoint": {"type": "string", "description": "接口路径，如 /v1/risk/score"},
            "minutes": {"type": "integer", "description": "时间窗口（分钟），默认 60"},
        },
    },
    func=query_recent_call_stats,
    category="logs",
))
