# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""工具调用中心：注册、schema、超时、重试、脱敏日志、高风险隔离。

- 每个工具声明 input schema、超时、重试、是否高风险。
- execute() 真实执行并写 tool_call_log（参数与结果脱敏）。
- 高风险工具不暴露给 AI（openai_tools 默认排除），只能人工/后台执行。
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.config import settings
from app.db import AsyncSessionLocal
from app.guardrail import desensitize
from app.models import ToolCallLog


@dataclass
class ToolContext:
    tenant_id: str
    trace_id: str = ""
    is_internal: bool = False


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON schema
    func: Callable[[dict, ToolContext], Awaitable[dict]]
    timeout: float = settings.tool_timeout_seconds
    retries: int = 1
    high_risk: bool = False
    category: str = "general"


REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    REGISTRY[spec.name] = spec
    return spec


def openai_tools(include_high_risk: bool = False) -> list[dict]:
    """返回可供 LLM function calling 的工具 schema（默认排除高风险）。"""
    tools = []
    for spec in REGISTRY.values():
        if spec.high_risk and not include_high_risk:
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
        )
    return tools


async def _log_call(ctx, name, args, result, status, duration_ms, error):
    async with AsyncSessionLocal() as s:
        s.add(
            ToolCallLog(
                trace_id=ctx.trace_id,
                tenant_id=ctx.tenant_id,
                tool_name=name,
                args_summary=desensitize.desensitize_text(json.dumps(args, ensure_ascii=False))[:1000],
                result_summary=desensitize.desensitize_text(json.dumps(result, ensure_ascii=False, default=str))[:1500],
                status=status,
                duration_ms=duration_ms,
                error_message=error,
            )
        )
        await s.commit()


async def execute(name: str, args: dict, ctx: ToolContext) -> dict:
    """执行工具：高风险拦截 + 超时 + 重试 + 脱敏日志。"""
    spec = REGISTRY.get(name)
    if spec is None:
        return {"ok": False, "error": f"未知工具: {name}"}

    # 高风险工具不允许 AI 直接执行（仅内部显式调用且需标记）
    if spec.high_risk and not ctx.is_internal:
        return {"ok": False, "error": f"工具 {name} 为高风险操作，需人工处理，AI 不可直接执行"}

    start = time.perf_counter()
    last_err = None
    for attempt in range(spec.retries + 1):
        try:
            data = await asyncio.wait_for(spec.func(args, ctx), timeout=spec.timeout)
            duration = int((time.perf_counter() - start) * 1000)
            result = {"ok": True, "data": data}
            await _log_call(ctx, name, args, data, "ok", duration, None)
            return result
        except asyncio.TimeoutError:
            last_err = f"工具调用超时(>{spec.timeout}s)"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
    duration = int((time.perf_counter() - start) * 1000)
    await _log_call(ctx, name, args, {}, "error", duration, last_err)
    return {"ok": False, "error": last_err}


def load_tools() -> None:
    """导入各工具模块以触发注册。"""
    from app.tools import apikey, billing_tools, logs, ticket_tools  # noqa: F401
