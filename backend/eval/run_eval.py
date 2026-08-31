# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""评估集运行器：真实跑多 Agent 链路并计算各项指标 + Badcase 归因。

指标：意图准确率、实体抽取准确率、引用率、转人工判定准确率、澄清判定准确率、脱敏准确率。
用法（backend 目录下）：python -m eval.run_eval
"""

import asyncio
import json
from pathlib import Path

from app.agents import supervisor
from app.cache.redis_client import get_redis
from app.guardrail import desensitize

EVAL_DIR = Path(__file__).resolve().parent


def _load(name: str) -> list[dict]:
    return [json.loads(l) for l in (EVAL_DIR / name).read_text(encoding="utf-8").splitlines() if l.strip()]


async def evaluate() -> dict:
    cases = _load("dataset.jsonl")
    # 清理语义缓存 + 路由缓存，保证每次评估走真实链路
    r = get_redis()
    for t in {c["tenant_id"] for c in cases}:
        await r.delete(f"semcache:{t}")
    async for k in r.scan_iter("routecache:*"):
        await r.delete(k)

    intent_ok = entity_total = entity_ok = 0
    cite_need = cite_ok = human_ok = clarify_ok = 0
    badcases = []

    for i, c in enumerate(cases):
        res = await supervisor.run(
            query=c["query"], tenant_id=c["tenant_id"], user_id=c["user_id"],
            conversation_id=f"eval_{c['id']}_{i}", is_internal=False,
        )
        # 意图
        intent_correct = res.get("intent") == c["expected_intent"]
        intent_ok += intent_correct
        # 实体
        for k, v in (c.get("expected_entities") or {}).items():
            entity_total += 1
            if res.get("entities", {}).get(k) == v:
                entity_ok += 1
        # 引用
        if c.get("expect_citations"):
            cite_need += 1
            if res.get("citations"):
                cite_ok += 1
        # 转人工
        human_correct = bool(res.get("need_human")) == bool(c.get("expect_human"))
        human_ok += human_correct
        # 澄清
        clarify_correct = bool(res.get("need_clarify")) == bool(c.get("expect_clarify", False))
        clarify_ok += clarify_correct

        if not (intent_correct and human_correct):
            badcases.append({
                "id": c["id"], "query": c["query"],
                "expected_intent": c["expected_intent"], "got_intent": res.get("intent"),
                "expect_human": bool(c.get("expect_human")), "got_human": bool(res.get("need_human")),
                "attribution": "意图识别" if not intent_correct else "转人工判定",
            })

    n = len(cases)
    # 脱敏评估
    sec = _load("security_set.jsonl")
    sec_ok = 0
    for s in sec:
        clean = desensitize.desensitize_text(s["text"])
        if not s["types"]:
            ok = clean == s["text"]
        else:
            ok = len(desensitize.detect(s["text"])) > 0 and len(desensitize.detect(clean)) == 0
        sec_ok += ok

    return {
        "total_cases": n,
        "intent_accuracy": round(intent_ok / n, 3),
        "entity_accuracy": round(entity_ok / entity_total, 3) if entity_total else None,
        "citation_rate": round(cite_ok / cite_need, 3) if cite_need else None,
        "human_transfer_accuracy": round(human_ok / n, 3),
        "clarify_accuracy": round(clarify_ok / n, 3),
        "desensitization_accuracy": round(sec_ok / len(sec), 3),
        "badcases": badcases,
    }


def main() -> None:
    from app.db import async_engine

    async def _run():
        m = await evaluate()
        print("==== 评估报告 ====")
        for k, v in m.items():
            if k != "badcases":
                print(f"  {k}: {v}")
        print(f"  badcases ({len(m['badcases'])}):")
        for b in m["badcases"]:
            print(f"    - {b['id']} [{b['attribution']}] {b['query'][:30]} "
                  f"intent {b['expected_intent']}→{b['got_intent']}")
        await async_engine.dispose()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
