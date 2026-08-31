# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""LLM 接入层：通义 DashScope（OpenAI 兼容）。

提供 chat（含 function calling）、流式 chat、embedding、rerank。
所有调用真实请求 DashScope；token 用量随结果返回，供成本统计。
"""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from functools import lru_cache

import dashscope
import openai
from openai import AsyncOpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

# 仅对瞬时错误重试（超时/连接/限流/5xx），避免对参数错误等无意义重试
_TRANSIENT = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)
_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    retry=retry_if_exception_type(_TRANSIENT),
    reraise=True,
)


@dataclass
class ChatResult:
    content: str
    tool_calls: list = field(default_factory=list)  # OpenAI 风格 tool_calls
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""


@lru_cache
def _client() -> AsyncOpenAI:
    if not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置，无法调用 LLM")
    return AsyncOpenAI(api_key=settings.dashscope_api_key, base_url=settings.llm_base_url)


@_retry
async def chat(
    messages: list[dict],
    *,
    model: str | None = None,
    tools: list[dict] | None = None,
    temperature: float = 0.2,
) -> ChatResult:
    """单轮/多轮对话。tools 非空时启用 function calling。瞬时错误自动重试。"""
    model = model or settings.llm_model_large
    kwargs: dict = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    resp = await _client().chat.completions.create(**kwargs)
    choice = resp.choices[0]
    usage = resp.usage
    tool_calls = []
    if choice.message.tool_calls:
        for tc in choice.message.tool_calls:
            tool_calls.append(
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
            )
    return ChatResult(
        content=choice.message.content or "",
        tool_calls=tool_calls,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
        total_tokens=usage.total_tokens if usage else 0,
        model=model,
    )


async def chat_stream(
    messages: list[dict], *, model: str | None = None, temperature: float = 0.3
) -> AsyncGenerator[str, None]:
    """流式对话，逐段产出文本。"""
    model = model or settings.llm_model_large
    stream = await _client().chat.completions.create(
        model=model, messages=messages, temperature=temperature, stream=True
    )
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


@_retry
async def embed(texts: list[str]) -> list[list[float]]:
    """文本向量化（text-embedding-v3）。瞬时错误自动重试。"""
    resp = await _client().embeddings.create(
        model=settings.embedding_model, input=texts, dimensions=settings.embedding_dim
    )
    return [d.embedding for d in resp.data]


async def embed_one(text: str) -> list[float]:
    return (await embed([text]))[0]


async def rerank(query: str, documents: list[str], top_n: int | None = None) -> list[dict]:
    """文档重排序（gte-rerank）。返回 [{index, score}]，按相关性降序。

    DashScope rerank 为同步 SDK，放入线程池避免阻塞事件循环。
    """
    if not documents:
        return []
    dashscope.api_key = settings.dashscope_api_key
    top_n = top_n or len(documents)

    def _call():
        return dashscope.TextReRank.call(
            model=settings.rerank_model,
            query=query,
            documents=documents,
            top_n=top_n,
            return_documents=False,
        )

    resp = await asyncio.to_thread(_call)
    results = []
    if resp and resp.output and resp.output.results:
        for r in resp.output.results:
            results.append({"index": r.index, "score": float(r.relevance_score)})
    return results
