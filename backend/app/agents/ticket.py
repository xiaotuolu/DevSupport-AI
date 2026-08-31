# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""Ticket Agent：兜底创建工单，附带 AI 诊断摘要与证据。"""

import json
from dataclasses import dataclass

from app.tools.registry import ToolContext, execute

# 意图 -> 工单类型 / 默认优先级
CATEGORY_MAP = {
    "api_error": ("API报错", "P1"),
    "rate_limit": ("API报错", "P1"),
    "billing": ("套餐账单", "P2"),
    "data_quality": ("数据质量", "P2"),
    "ticket": ("故障投诉", "P2"),
    "doc_qa": ("咨询", "P3"),
}


@dataclass
class TicketResult:
    ticket_id: str | None
    message: str


async def create_from_context(
    *,
    query: str,
    intent: str,
    entities: dict,
    ai_diagnosis: str,
    evidence: dict,
    ctx: ToolContext,
    user_id: str,
    conversation_id: str,
) -> TicketResult:
    # 按意图映射工单类型与优先级，未知意图按低优先级咨询处理
    category, priority = CATEGORY_MAP.get(intent, ("咨询", "P3"))
    request_ids = [entities["request_id"]] if entities.get("request_id") else []
    title = query.strip()[:60] or f"{category}工单"

    args = {
        "title": title,
        "category": category,
        "priority": priority,
        "summary": query.strip()[:500],
        "related_request_ids": request_ids,
        "related_endpoint": entities.get("endpoint"),
        "error_code": entities.get("error_code"),
        "evidence": json.dumps(evidence, ensure_ascii=False)[:2000],
        "ai_diagnosis": (ai_diagnosis or "")[:2000],
        "user_id": user_id,
        "conversation_id": conversation_id,
    }
    # 经工具中心建单，证据与诊断随单落库，人工接手即可看到完整上下文
    r = await execute("create_ticket", args, ctx)
    if not r["ok"]:
        return TicketResult(ticket_id=None, message=f"工单创建失败：{r.get('error')}")
    tid = r["data"]["ticket_id"]
    return TicketResult(
        ticket_id=tid,
        message=f"已为你创建工单 {tid}（{category}，优先级 {priority}），技术支持会尽快跟进。",
    )
