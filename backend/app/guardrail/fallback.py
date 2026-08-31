# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""多级兜底策略。

层级：
1. LLM 瞬时失败 → 自动重试（见 llm.client 的 @_retry）。
2. 单个 Agent 异常 → 在编排中被 try/except 隔离，不影响整体。
3. RAG 无命中 → doc_rag 返回不确定提示并建议转人工。
4. 意图低置信 / 缺关键信息 → 进入澄清追问。
5. 工具超时/失败 → registry 返回降级结果，Agent 据此提示证据不足并可建单。
6. 用户要求人工 / 高风险操作 → 创建工单转人工。
7. 整个编排不可恢复异常 → 规则兜底回复 + 自动建单（本模块）。
"""

# 不可恢复失败时的规则兜底话术（按意图）
RULE_REPLIES = {
    "api_error": "抱歉，诊断服务暂时不可用。我已为你登记问题并转交人工技术支持，请稍候。",
    "rate_limit": "抱歉，诊断服务暂时不可用。常见的 429 处理是本地限速 + 指数退避重试，必要时升级套餐。我已转交人工进一步核查。",
    "billing": "抱歉，账单服务暂时不可用。我已登记你的账单问题并转交人工处理。",
    "data_quality": "抱歉，处理服务暂时不可用。我已登记你的数据质量问题并转交人工核查。",
    "doc_qa": "抱歉，问答服务暂时不可用，请稍后重试，或转人工技术支持。",
    "ticket": "已收到你的请求，正在为你转接人工技术支持。",
    "chitchat": "抱歉，我现在有点忙，请稍后再试。",
}

DEFAULT_RULE_REPLY = "抱歉，服务暂时不可用。我已登记你的问题并转交人工技术支持，请稍候。"


def rule_reply(intent: str | None) -> str:
    return RULE_REPLIES.get(intent or "", DEFAULT_RULE_REPLY)
