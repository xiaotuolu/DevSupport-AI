# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""Intent Router Agent：意图分类 + 实体抽取 + 推荐路由。"""

import json
import re

from app.llm import client
from app.llm.router import model_for

# 意图 -> 推荐专业 Agent
ROUTE_MAP = {
    "doc_qa": ["doc_rag"],
    "api_error": ["api_diagnostic", "doc_rag"],
    "rate_limit": ["api_diagnostic", "billing", "doc_rag"],  # 429 复合问题
    "billing": ["billing", "doc_rag"],
    "data_quality": ["api_diagnostic", "doc_rag"],
    "ticket": ["ticket"],
    "chitchat": [],
}

INTENTS = list(ROUTE_MAP.keys())

_SYS = (
    "你是 API 平台技术支持的意图识别器。判断用户问题的意图类型并抽取关键实体。\n"
    f"意图类型（只能选其一）：{INTENTS}\n"
    "- doc_qa: 询问文档/概念/用法/如何做/如何排查/错误码含义。包括「Webhook 回调如何排查」「签名怎么生成」等操作指导。\n"
    "- api_error: 针对某次具体调用的报错要做诊断定位（401/403/500/签名/参数等），通常带 request_id 或明确错误码/状态码。\n"
    "- rate_limit: 只要涉及 429 / QPS 超限 / 限流 / 大量请求被拒，一律归此类（即使提到了接口名）。\n"
    "- billing: 套餐/调用量/余额/账单/发票/费用/QPS上限与配额规则。\n"
    "- data_quality: 返回为空/数据不一致/字段缺失等数据质量问题。\n"
    "- ticket: 明确要求人工、投诉、查询工单。\n"
    "- chitchat: 与业务无关的闲聊。\n"
    "消歧规则：提到 429/限流→rate_limit；问「怎么排查/如何配置/是什么含义」的指导类→doc_qa；"
    "只有要定位某次具体失败(带request_id或明确错误码)才用 api_error；"
    "退款/改价/套餐升降级/变更等商业诉求→billing（由账单模块说明并转人工），不要归 ticket；"
    "ticket 仅用于明确要求人工、投诉或查询既有工单。\n"
    "示例：\n"
    "  「下午很多429是不是挂了」→ rate_limit\n"
    "  「Webhook 回调收不到怎么排查」→ doc_qa\n"
    "  「SIGN_INVALID 是什么原因」→ doc_qa\n"
    "  「接口返回401，request_id是req_x」→ api_error\n"
    "实体字段（无则留空字符串）：request_id, error_code, http_status, endpoint, app_id, month(YYYY-MM), webhook_event_id, invoice_id, ticket_id\n"
    "实体规则：http_status 只放数字状态码(如 401/429/500)；error_code 只放大写字母下划线错误码(如 AUTH_KEY_EXPIRED/SIGN_INVALID)，"
    "不要把数字状态码填进 error_code；endpoint 形如 /v1/idcard/verify。\n"
    "只输出 JSON：{\"intent\":..., \"confidence\":0~1, \"entities\":{...}}"
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

# 强模式实体的正则兜底（LLM 偶尔漏抽，规则补齐更稳）
_ENTITY_RE = {
    "request_id": re.compile(r"\breq_[0-9A-Za-z_]+\b"),
    "error_code": re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b"),
    "endpoint": re.compile(r"/v\d+/[A-Za-z0-9/_-]+"),
    "http_status": re.compile(r"\b[1-5]\d{2}\b"),
}


def _regex_entities(query: str) -> dict:
    found = {}
    for key, pat in _ENTITY_RE.items():
        m = pat.search(query)
        if m:
            found[key] = m.group(0)
    return found


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    m = _JSON_RE.search(text)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


async def classify(query: str, history: list[dict] | None = None) -> dict:
    """对单条 query 做意图分类 + 实体抽取，返回意图/置信度/实体/推荐路由。"""
    msgs = [{"role": "system", "content": _SYS}]
    if history:
        # 仅带最近 4 条历史，兼顾多轮指代消解与 token 成本
        hist_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:])
        msgs.append({"role": "user", "content": f"对话历史：\n{hist_text}"})
    msgs.append({"role": "user", "content": f"用户问题：{query}"})

    # temperature=0 保证分类稳定可复现
    r = await client.chat(msgs, model=model_for("intent"), temperature=0.0)
    parsed = _parse_json(r.content)

    intent = parsed.get("intent", "doc_qa")
    if intent not in ROUTE_MAP:  # LLM 给出非法意图时回落到文档问答
        intent = "doc_qa"
    entities = {k: v for k, v in (parsed.get("entities") or {}).items() if v}
    # 正则兜底：强模式实体未被 LLM 抽到时补齐
    for k, v in _regex_entities(query).items():
        entities.setdefault(k, v)
    try:
        confidence = float(parsed.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5

    return {
        "intent": intent,
        "confidence": confidence,
        "entities": entities,
        "route": ROUTE_MAP[intent],
        "tokens": r.total_tokens,
    }
