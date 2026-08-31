# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""API Diagnostic Agent：基于调用日志/Key状态/限流统计 + 文档，辅助定位 API 报错。

输出结构：诊断结论 / 证据摘要 / 可能原因 / 建议操作 / 关联文档 / 是否需要工单。
"""

import asyncio
import json
from dataclasses import dataclass, field

from app.agents import doc_rag
from app.agents.util import normalize_card, parse_json, render_card
from app.db import AsyncSessionLocal
from app.llm import client
from app.llm.router import model_for
from app.models import ErrorCode
from app.tools.registry import ToolContext, execute


async def _error_doc_fast(error_code: str):
    """已知错误码直接查 error_code 表，跳过完整 RAG（性能优化热路径）。"""
    async with AsyncSessionLocal() as s:
        row = await s.get(ErrorCode, error_code)
    if not row:
        return None
    answer = f"{row.code}（{row.name}）：{row.cause} 处理步骤：{row.fix_steps}"
    citations = [{"index": 1, "doc_title": "错误码手册", "section": row.code, "version": "v1", "score": 1.0}]
    return answer, citations


@dataclass
class DiagResult:
    answer: str
    evidence: dict = field(default_factory=dict)
    citations: list[dict] = field(default_factory=list)
    error_code: str | None = None
    need_ticket: bool = False
    tokens: int = 0
    card: dict | None = None


async def diagnose(query: str, entities: dict, ctx: ToolContext, *, is_rate_limit: bool = False) -> DiagResult:
    """收集证据（日志/Key/限流统计）+ 文档，交 LLM 组装结构化诊断卡片。"""
    evidence: dict = {}
    error_code = entities.get("error_code")
    endpoint = entities.get("endpoint")
    request_id = entities.get("request_id")

    # 1. 有 request_id → 先查调用日志（后续步骤依赖其 error_code/endpoint/app_id）
    app_id = None
    if request_id:
        r = await execute("query_call_log", {"request_id": request_id}, ctx)
        if r["ok"] and r["data"].get("found"):
            log = r["data"]
            evidence["call_log"] = log
            error_code = error_code or log.get("error_code")
            endpoint = endpoint or log.get("endpoint")
            app_id = log.get("app_id")
        else:
            evidence["call_log"] = {"found": False, "request_id": request_id}

    # 2. 性能优化：Key 状态查询、限流统计、文档支撑 三者并行
    need_apikey = error_code in ("AUTH_KEY_EXPIRED", "AUTH_KEY_INVALID") and app_id
    need_stats = is_rate_limit or error_code in ("RATE_LIMIT_EXCEEDED", "QUOTA_EXCEEDED") or bool(endpoint)

    async def _apikey():
        return await execute("query_apikey_status", {"app_id": app_id}, ctx) if need_apikey else None

    async def _stats():
        return await execute("query_recent_call_stats", {"endpoint": endpoint, "minutes": 60}, ctx) if need_stats else None

    async def _doc():
        # 热路径：已知错误码直查 error_code 表，跳过 RAG 的 embed/rerank/generate
        if error_code:
            fast = await _error_doc_fast(error_code)
            if fast:
                return ("fast", fast[0], fast[1], 0)
        d = await doc_rag.answer(
            f"{error_code} 含义、原因与处理步骤" if error_code else query,
            error_code=error_code or None,
        )
        return ("rag", d.answer, d.citations, d.tokens)

    rk, rs, doc_res = await asyncio.gather(_apikey(), _stats(), _doc())
    if rk and rk["ok"]:
        evidence["apikey_status"] = rk["data"]
    if rs and rs["ok"] and rs["data"].get("total"):
        evidence["recent_stats"] = rs["data"]
    _, doc_answer, citations, doc_tokens = doc_res

    # 5. LLM 组装结构化诊断（JSON 卡片）
    sys = (
        "你是 API 平台诊断助手。基于【证据】(真实调用日志/Key状态/限流统计)和【文档】输出结构化诊断。"
        "只能依据证据与文档，不得编造；涉及密钥只展示脱敏值。\n"
        "输出 JSON：{\"conclusion\":\"一句话诊断结论\", \"evidence\":[\"关键证据(含状态码/错误码/时间/脱敏Key等)\"], "
        "\"steps\":[\"可执行修复步骤\"], \"need_ticket\":true/false}。need_ticket：证据不足以定位或需人工时为 true。只输出 JSON。"
    )
    user = (
        f"【用户问题】{query}\n\n"
        f"【证据】{json.dumps(evidence, ensure_ascii=False)}\n\n"
        f"【文档】{doc_answer}"
    )
    gen = await client.chat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        model=model_for("diagnose"),
        temperature=0.2,
    )
    parsed = parse_json(gen.content)
    card = normalize_card(parsed)
    need_ticket = bool(parsed.get("need_ticket", False))
    # 证据不足（无有效日志）也建议工单
    if request_id and not evidence.get("call_log", {}).get("found", False):
        need_ticket = True
    if not card["conclusion"]:
        card["conclusion"] = gen.content.strip()[:200]

    return DiagResult(
        answer=render_card(card),
        evidence=evidence,
        citations=citations,
        error_code=error_code,
        need_ticket=need_ticket,
        tokens=gen.total_tokens + doc_tokens,
        card=card,
    )
