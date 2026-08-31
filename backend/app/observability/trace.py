# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""AgentTrace 链路采集与持久化。

每次请求生成 trace_id，逐节点记录耗时/token/命中文档/状态，最终落库 agent_trace。
"""

import time
import uuid

from app.db import AsyncSessionLocal
from app.models import AgentTrace


class TraceCollector:
    def __init__(self, tenant_id: str, conversation_id: str | None = None):
        self.trace_id = "trace_" + uuid.uuid4().hex[:16]
        self.tenant_id = tenant_id
        self.conversation_id = conversation_id
        self.message_id: str | None = None
        self.steps: list[dict] = []
        self._order = 0

    def step(
        self,
        agent_name: str,
        *,
        input_summary: str = "",
        output_summary: str = "",
        status: str = "ok",
        duration_ms: int = 0,
        token_usage: int = 0,
        hit_docs: list | None = None,
        error: str | None = None,
    ) -> None:
        """记录一个编排节点的执行情况，step_order 自增以还原链路顺序。"""
        self._order += 1
        self.steps.append(
            {
                "agent_name": agent_name,
                "step_order": self._order,
                "input_summary": input_summary[:500],
                "output_summary": output_summary[:500],
                "status": status,
                "duration_ms": duration_ms,
                "token_usage": token_usage,
                "hit_docs": hit_docs or [],
                "error_message": error,
            }
        )

    @property
    def total_tokens(self) -> int:
        return sum(s["token_usage"] for s in self.steps)

    async def persist(self, message_id: str | None = None) -> None:
        async with AsyncSessionLocal() as s:
            for step in self.steps:
                s.add(
                    AgentTrace(
                        trace_id=self.trace_id,
                        conversation_id=self.conversation_id,
                        message_id=message_id or self.message_id,
                        tenant_id=self.tenant_id,
                        **step,
                    )
                )
            await s.commit()


class timer:
    """上下文管理器：测量耗时（毫秒）。"""

    def __enter__(self):
        self._t = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = int((time.perf_counter() - self._t) * 1000)
        return False
