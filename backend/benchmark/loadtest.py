# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""并发压测：测 P50/P95/吞吐，并基于 AgentTrace 做阶段耗时分解。

对比「冷启动(无缓存)」与「缓存预热」两轮，量化语义缓存的优化效果。
用法（backend 目录下）：python -m benchmark.loadtest
"""

import asyncio
import statistics
import time

from sqlalchemy import select

from app.agents import supervisor
from app.cache.redis_client import get_redis
from app.db import AsyncSessionLocal, async_engine
from app.models import AgentTrace

# 标准压测问题（以可缓存的文档问答为主，混合诊断/账单）
QUESTIONS = [
    ("签名算法怎么生成？", "t_acme", "u_acme_dev"),
    ("Webhook 回调收不到怎么排查", "t_acme", "u_acme_dev"),
    ("429 限流了怎么办", "t_acme", "u_acme_dev"),
    ("接入 API 的流程是什么", "t_acme", "u_acme_dev"),
    ("账单费用是怎么计算的", "t_acme", "u_acme_dev"),
    ("SIGN_INVALID 是什么原因", "t_acme", "u_acme_dev"),
]

CONCURRENCY = 4
REPEAT = 2  # 每个问题重复次数，放大并发量


def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


async def _run_batch(label: str) -> tuple[list[float], list[str]]:
    sem = asyncio.Semaphore(CONCURRENCY)
    latencies: list[float] = []
    trace_ids: list[str] = []
    queries = [q for q in QUESTIONS for _ in range(REPEAT)]

    async def one(idx: int, q, tenant, user):
        async with sem:
            t0 = time.perf_counter()
            r = await supervisor.run(query=q, tenant_id=tenant, user_id=user,
                                     conversation_id=f"bench_{label}_{idx}")
            dt = time.perf_counter() - t0
            latencies.append(dt)
            trace_ids.append(r["trace_id"])
            return r.get("from_cache", False)

    t0 = time.perf_counter()
    flags = await asyncio.gather(*[one(i, q, t, u) for i, (q, t, u) in enumerate(queries)])
    wall = time.perf_counter() - t0
    cache_hits = sum(1 for f in flags if f)
    print(f"\n[{label}] 请求数={len(queries)} 并发={CONCURRENCY} 总耗时={wall:.2f}s "
          f"吞吐={len(queries)/wall:.2f} req/s 缓存命中={cache_hits}")
    print(f"  延迟 P50={_percentile(latencies,50):.2f}s P95={_percentile(latencies,95):.2f}s "
          f"avg={statistics.mean(latencies):.2f}s max={max(latencies):.2f}s")
    return latencies, trace_ids


async def _stage_breakdown(trace_ids: list[str]) -> None:
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(select(AgentTrace).where(AgentTrace.trace_id.in_(trace_ids)))
        ).scalars().all()
    agg: dict[str, list[int]] = {}
    for r in rows:
        agg.setdefault(r.agent_name, []).append(r.duration_ms)
    print("  阶段平均耗时(ms):")
    for name, ds in sorted(agg.items(), key=lambda x: -statistics.mean(x[1])):
        print(f"    {name:18s} avg={statistics.mean(ds):7.0f}  count={len(ds)}")


async def main() -> None:
    r = get_redis()
    await r.delete("semcache:t_acme")

    # 冷启动（缓存空）
    cold_lat, cold_traces = await _run_batch("冷启动-无缓存")
    await _stage_breakdown(cold_traces)

    # 缓存预热后再跑（doc_qa 命中缓存）
    warm_lat, _ = await _run_batch("缓存预热")

    p95_cold, p95_warm = _percentile(cold_lat, 95), _percentile(warm_lat, 95)
    print(f"\n==== 优化对比 ====\n  P95: 冷启动 {p95_cold:.2f}s -> 预热 {p95_warm:.2f}s "
          f"(降低 {(1-p95_warm/p95_cold)*100:.0f}%)")
    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
