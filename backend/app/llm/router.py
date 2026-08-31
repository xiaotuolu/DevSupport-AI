# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""模型分层路由：简单任务走小模型降本降延迟，复杂任务走大模型保质量。"""

from app.config import settings

# 任务 -> 模型档位
_SMALL_TASKS = {"intent", "clarify", "chitchat", "route", "cache_match"}
_LARGE_TASKS = {"diagnose", "summarize", "rag_generate", "billing_explain"}


def model_for(task: str) -> str:
    """根据任务类型返回模型名。未知任务默认大模型（偏保守）。"""
    if task in _SMALL_TASKS:
        return settings.llm_model_small
    return settings.llm_model_large
