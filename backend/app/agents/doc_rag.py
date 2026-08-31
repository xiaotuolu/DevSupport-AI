# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""Doc RAG Agent：检索增强问答。

流程：Query 改写 → 混合检索 → Rerank → 上下文压缩 → 带引用生成 → 无命中兜底。
"""

from dataclasses import dataclass, field

from app.agents.util import normalize_card, parse_json, render_card
from app.config import settings
from app.llm import client
from app.llm.router import model_for
from app.rag import compressor, reranker, retriever

NO_HIT_MESSAGE = (
    "抱歉，我在现有文档中没有找到能确定回答这个问题的依据。"
    "为避免给你错误信息，建议转人工技术支持进一步确认，我可以帮你创建工单。"
)


@dataclass
class RagResult:
    answer: str
    hit: bool
    citations: list[dict] = field(default_factory=list)
    candidates: int = 0
    top_score: float = 0.0
    tokens: int = 0
    card: dict | None = None


async def _rewrite_query(query: str, history: list[dict] | None) -> str:
    """结合历史把指代/省略补全为独立查询；无历史则原样返回。"""
    if not history:
        return query
    hist_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:])
    prompt = [
        {"role": "system", "content": "你是检索查询改写器。根据对话历史，把用户最新问题改写为一句不依赖上下文的完整检索查询，只输出改写后的查询本身。"},
        {"role": "user", "content": f"对话历史：\n{hist_text}\n\n最新问题：{query}\n\n改写后的查询："},
    ]
    r = await client.chat(prompt, model=model_for("intent"), temperature=0.0)
    rewritten = r.content.strip()
    return rewritten or query


async def answer(
    query: str,
    *,
    history: list[dict] | None = None,
    error_code: str | None = None,
    top_n: int = 5,
) -> RagResult:
    # 1. Query 改写
    search_query = await _rewrite_query(query, history)

    # 2. 混合检索
    candidates, top_vec = await retriever.hybrid_search(search_query, error_code=error_code)
    if not candidates:
        return RagResult(answer=NO_HIT_MESSAGE, hit=False)

    # 3. Rerank 精排
    reranked = await reranker.rerank_candidates(search_query, candidates, top_n=top_n)
    top_score = reranked[0]["rerank_score"] if reranked else 0.0

    # 4. 无命中判定：rerank 绝对分对换述相关问题不稳，故用"向量余弦 OR rerank"双信号。
    #    覆盖到的问题向量余弦显著高于无关问题；rerank 高分也直接判命中。
    hit = bool(reranked) and (top_vec >= settings.rag_vec_hit_threshold or top_score >= settings.rag_score_threshold)
    if not hit:
        return RagResult(
            answer=NO_HIT_MESSAGE, hit=False, candidates=len(candidates), top_score=top_score
        )

    # 5. 上下文压缩 + 引用
    kept = compressor.compress(reranked)
    context, citations = compressor.build_context(kept)

    # 6. 带引用生成（结构化卡片）
    sys_prompt = (
        "你是 API 平台的技术支持助手。只能基于【参考资料】回答，不得编造文档之外的接口能力。"
        "若资料不足以回答，conclusion 中明确说明不确定。涉及费用/合同以后台数据和正式合同为准。\n"
        "输出 JSON：{\"conclusion\":\"直接回答/结论\", \"steps\":[\"关键说明或可执行步骤\"]}。只输出 JSON。"
    )
    user_prompt = f"【参考资料】\n{context}\n\n【用户问题】\n{query}"
    gen = await client.chat(
        [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}],
        model=model_for("rag_generate"),
        temperature=0.2,
    )
    card = normalize_card(parse_json(gen.content))
    if not card["conclusion"]:
        card["conclusion"] = gen.content.strip()[:300]
    return RagResult(
        answer=render_card(card),
        hit=True,
        citations=citations,
        candidates=len(candidates),
        top_score=top_score,
        tokens=gen.total_tokens,
        card=card,
    )
