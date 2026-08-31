# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""Billing Agent：套餐/调用量/账单解释；高风险商业操作转人工。"""

import json
from dataclasses import dataclass, field

from app.agents import doc_rag
from app.agents.util import normalize_card, parse_json, render_card
from app.llm import client
from app.llm.router import model_for
from app.tools.registry import ToolContext, execute

# 高风险商业意图关键词（不直接执行，转人工）
HIGH_RISK_KEYWORDS = [
    "退款", "退费", "改价", "调价", "重置",
    "降套餐", "降级", "降到", "升到", "改成", "套餐变更", "变更套餐",
    "改套餐", "换套餐", "退订", "解约", "取消套餐",
]


@dataclass
class BillingResult:
    answer: str
    evidence: dict = field(default_factory=dict)
    citations: list[dict] = field(default_factory=list)
    need_human: bool = False
    tokens: int = 0
    card: dict | None = None


async def handle(query: str, entities: dict, ctx: ToolContext) -> BillingResult:
    """查套餐/用量/账单真实数据 + 计费文档，LLM 解释；高风险操作标记转人工。"""
    # 命中高风险商业关键词则只解释、不执行，最终标记 need_human
    high_risk = any(k in query for k in HIGH_RISK_KEYWORDS)

    evidence: dict = {}
    # 套餐
    rp = await execute("query_plan", {}, ctx)
    if rp["ok"] and rp["data"].get("found"):
        evidence["plan"] = rp["data"]
    # 用量（指定月或全部）
    month = entities.get("month")
    ru = await execute("query_usage", {"month": month} if month else {}, ctx)
    if ru["ok"] and ru["data"].get("found"):
        evidence["usage"] = ru["data"]["usage"]
    # 账单
    rb = await execute("query_bill", {"month": month} if month else {}, ctx)
    if rb["ok"] and rb["data"].get("found"):
        evidence["bills"] = rb["data"]["bills"]

    # 计费规则文档
    doc = await doc_rag.answer("套餐计费规则、账单费用构成与超额计费")
    citations = doc.citations

    sys = (
        "你是 API 平台账单助手。基于【证据】(真实套餐/用量/账单数据)与【文档】解释账单/套餐问题。"
        "必须直接使用证据中的真实数字（套餐配额、各月调用量、基础/超额费用），不要说无法查看数据。"
        "账单上涨要对比月度用量并说明费用构成(基础费用 vs 超额费用)。"
        "退款、改价、套餐升降级等商业操作不能直接执行，需说明将转人工/商务。\n"
        "输出 JSON：{\"conclusion\":\"一句话结论\", \"evidence\":[\"引用到的真实数据点\"], \"steps\":[\"建议操作\"]}。只输出 JSON。"
    )
    risk_note = "\n注意：用户请求涉及高风险商业操作，结论中需明确告知不能直接执行、将转人工/商务跟进。" if high_risk else ""
    user = (
        f"【用户问题】{query}{risk_note}\n\n"
        f"【证据】{json.dumps(evidence, ensure_ascii=False)}\n\n"
        f"【文档】{doc.answer}"
    )
    gen = await client.chat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        model=model_for("billing_explain"),
        temperature=0.2,
    )
    card = normalize_card(parse_json(gen.content))
    if not card["conclusion"]:
        card["conclusion"] = gen.content.strip()[:200]
    return BillingResult(
        answer=render_card(card),
        evidence=evidence,
        citations=citations,
        need_human=high_risk,
        tokens=gen.total_tokens + doc.tokens,
        card=card,
    )
