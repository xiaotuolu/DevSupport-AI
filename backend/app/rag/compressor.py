# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""上下文压缩：在 token 预算内保留最相关片段，降低生成成本。

策略（无需额外 LLM 调用，低成本）：
1. 丢弃 rerank 分数低于阈值的片段（弱相关噪声）。
2. 按相关性从高到低累加，直到达到字符预算上限。
"""

DEFAULT_BUDGET_CHARS = 1800
MIN_RERANK_SCORE = 0.05


def compress(chunks: list[dict], budget_chars: int = DEFAULT_BUDGET_CHARS) -> list[dict]:
    """返回压缩后的片段列表（保序：按相关性）。"""
    kept, used = [], 0
    for c in chunks:
        if c.get("rerank_score", 1.0) < MIN_RERANK_SCORE:
            continue
        length = len(c["content"])
        if used + length > budget_chars and kept:
            break
        kept.append(c)
        used += length
    return kept


def build_context(chunks: list[dict]) -> tuple[str, list[dict]]:
    """拼接上下文文本并返回引用清单。"""
    blocks, citations = [], []
    for i, c in enumerate(chunks, 1):
        tag = f"[{i}] 《{c['doc_title']}》- {c['section']}"
        blocks.append(f"{tag}\n{c['content']}")
        citations.append(
            {
                "index": i,
                "doc_title": c["doc_title"],
                "section": c["section"],
                "version": c.get("version", "v1"),
                "score": round(c.get("rerank_score", 0.0), 3),
            }
        )
    return "\n\n".join(blocks), citations
