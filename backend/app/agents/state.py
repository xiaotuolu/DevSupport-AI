# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""LangGraph 编排状态。"""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # 输入与上下文
    tenant_id: str
    user_id: str
    conversation_id: str
    is_internal: bool
    query: str
    history: list[dict]              # 历史消息 [{role, content}]
    collected_entities: dict         # 记忆中已收集的实体

    # 意图识别
    intent: str
    confidence: float
    entities: dict
    route: list[str]                 # 选中的专业 Agent
    need_clarify: bool
    clarify_question: str

    # 处理结果
    agent_outputs: dict[str, Any]    # 各专业 Agent 输出
    rag_citations: list[dict]
    draft_answer: str
    final_answer: str
    card: dict | None
    need_human: bool
    pending_ticket: bool        # 是否需要建单（诊断证据不足等）
    ticket_id: str
    ticket_message: str         # 建单后给客户的友好提示

    # 可观测
    trace_id: str
    total_tokens: int
