# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""对话/工单相关 DTO。"""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class FeedbackRequest(BaseModel):
    conversation_id: str
    message_id: str | None = None
    type: str  # resolved / unresolved / need_human


class TicketUpdateRequest(BaseModel):
    status: str | None = None
    assignee: str | None = None
    note: str | None = None
