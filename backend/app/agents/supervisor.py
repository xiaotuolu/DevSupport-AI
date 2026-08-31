# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""Supervisor：用 LangGraph 编排多 Agent，串行保证安全审查在最终回复前。

管线：load_context → intent → [clarify?] → specialists(并行) → ticket → summarize → security
每个节点记录 AgentTrace；任一专业 Agent 异常被隔离降级，不影响整体。
"""

import asyncio

from langgraph.graph import END, START, StateGraph

from app.agents import api_diagnostic, billing, doc_rag, intent_router, security, ticket
from app.agents.state import AgentState
from app.agents.util import render_card
from app.cache import route_cache, semantic_cache
from app.config import settings
from app.guardrail import fallback
from app.llm import client
from app.llm.router import model_for
from app.memory import session
from app.observability import cost
from app.observability.trace import TraceCollector, timer
from app.tools.registry import ToolContext, load_tools

load_tools()


async def _general_reply(query: str) -> tuple[str, int]:
    r = await client.chat(
        [
            {"role": "system", "content": "你是 API 平台技术支持助手。对与业务无关的闲聊，礼貌简短回应，并引导用户提出 API 接入/报错/账单等技术支持问题。"},
            {"role": "user", "content": query},
        ],
        model=model_for("chitchat"),
        temperature=0.5,
    )
    return r.content.strip(), r.total_tokens


def build_graph(ctx: ToolContext, trace: TraceCollector):
    """按请求构建图（闭包捕获 ctx 与 trace）。"""

    async def load_context(state: AgentState) -> dict:
        conv = state["conversation_id"]
        history = await session.get_history(conv)
        entities = await session.get_entities(conv)
        return {"history": history, "collected_entities": entities}

    async def intent_node(state: AgentState) -> dict:
        history = state.get("history")
        with timer() as t:
            cached_route = None if history else await route_cache.get(state["query"])
            if cached_route:
                res = {**cached_route, "tokens": 0}
            else:
                res = await intent_router.classify(state["query"], history)
                if not history:
                    await route_cache.put(state["query"], res)
        # 合并记忆中的实体（新抽取覆盖/补充）
        merged = await session.update_entities(state["conversation_id"], res["entities"])
        trace.step(
            "intent_router",
            input_summary=state["query"],
            output_summary=f"intent={res['intent']} conf={res['confidence']} entities={merged}",
            duration_ms=t.ms,
            token_usage=res["tokens"],
        )
        # 澄清判定：API 报错/数据质量类缺关键定位信息时追问
        need_clarify = False
        clarify_q = ""
        if res["intent"] == "api_error" and not merged.get("request_id") and not merged.get("error_code"):
            need_clarify = True
            clarify_q = "为帮你准确定位，请提供以下任一信息：request_id、出错的接口名，或返回的错误码/HTTP状态码（最多 3 项即可）。"
        elif res["confidence"] < settings.intent_confidence_threshold and res["intent"] != "chitchat":
            need_clarify = True
            clarify_q = "我不太确定你的问题类型，能补充一下具体场景吗？比如是接口报错、账单费用，还是文档用法？"
        return {
            "intent": res["intent"],
            "confidence": res["confidence"],
            "entities": merged,
            "route": res["route"],
            "need_clarify": need_clarify,
            "clarify_question": clarify_q,
        }

    def after_intent(state: AgentState) -> str:
        return "clarify" if state.get("need_clarify") else "specialists"

    async def clarify_node(state: AgentState) -> dict:
        trace.step("clarify", input_summary=state["query"], output_summary=state["clarify_question"])
        return {"final_answer": state["clarify_question"], "need_human": False}

    async def _run_agent(name: str, coro):
        with timer() as t:
            try:
                result = await coro
                return name, result, t, None
            except Exception as e:  # noqa: BLE001  单 Agent 异常隔离
                return name, None, t, f"{type(e).__name__}: {e}"

    async def specialists_node(state: AgentState) -> dict:
        route = state.get("route", [])
        query, entities = state["query"], state.get("entities", {})
        outputs: dict = {}
        citations: list = []
        need_human = False
        need_ticket = False

        if not route:  # chitchat
            with timer() as t:
                reply, tok = await _general_reply(query)
            trace.step("general", input_summary=query, output_summary=reply[:120], duration_ms=t.ms, token_usage=tok)
            return {"agent_outputs": {"general": reply}, "rag_citations": []}

        # 并行运行选中的专业 Agent
        coros = []
        if "api_diagnostic" in route:
            coros.append(_run_agent("api_diagnostic", api_diagnostic.diagnose(
                query, entities, ctx, is_rate_limit=state["intent"] == "rate_limit")))
        if "billing" in route:
            coros.append(_run_agent("billing", billing.handle(query, entities, ctx)))
        # doc_rag 仅在没有诊断/账单作为主答时单独使用，避免重复（诊断/账单内部已含文档）
        if "doc_rag" in route and not ("api_diagnostic" in route or "billing" in route):
            coros.append(_run_agent("doc_rag", doc_rag.answer(query, history=state.get("history"))))

        results = await asyncio.gather(*coros)
        for name, result, t, err in results:
            if err:
                trace.step(name, input_summary=query, status="error", duration_ms=t.ms, error=err)
                continue
            tok = getattr(result, "tokens", 0)
            hit = [c.get("doc_title") for c in getattr(result, "citations", [])]
            trace.step(name, input_summary=query, output_summary=getattr(result, "answer", "")[:160],
                       duration_ms=t.ms, token_usage=tok, hit_docs=hit)
            outputs[name] = result
            citations.extend(getattr(result, "citations", []))
            if getattr(result, "need_human", False):
                need_human = True
            if getattr(result, "need_ticket", False):
                need_ticket = True

        return {
            "agent_outputs": outputs,
            "rag_citations": citations,
            "need_human": need_human or state["intent"] == "ticket",
            "pending_ticket": need_ticket,
        }

    async def ticket_node(state: AgentState) -> dict:
        outputs = state.get("agent_outputs", {})
        need_ticket = state.get("pending_ticket") or state.get("need_human")
        if not need_ticket:
            return {}
        # 汇总现有诊断作为工单上下文
        ai_diag = ""
        evidence = {}
        if "api_diagnostic" in outputs:
            ai_diag = outputs["api_diagnostic"].answer
            evidence = outputs["api_diagnostic"].evidence
        elif "billing" in outputs:
            ai_diag = outputs["billing"].answer
            evidence = outputs["billing"].evidence
        with timer() as t:
            tk = await ticket.create_from_context(
                query=state["query"], intent=state["intent"], entities=state.get("entities", {}),
                ai_diagnosis=ai_diag, evidence=evidence, ctx=ctx,
                user_id=state.get("user_id", ""), conversation_id=state["conversation_id"])
        trace.step("ticket", input_summary=state["query"], output_summary=tk.message, duration_ms=t.ms)
        return {"ticket_id": tk.ticket_id, "ticket_message": tk.message}

    async def summarize_node(state: AgentState) -> dict:
        outputs = state.get("agent_outputs", {})
        cards = []
        for name in ("api_diagnostic", "billing", "doc_rag"):
            o = outputs.get(name)
            if o is not None and getattr(o, "card", None):
                cards.append(o.card)
        general = outputs.get("general")

        card = None
        if general and not cards:
            draft = general
        elif len(cards) == 1:
            card = cards[0]
            draft = render_card(card)
        elif len(cards) > 1:
            # 复合问题（如 429）：小模型合并多条结论，证据/步骤取并集
            with timer() as t:
                gen = await client.chat(
                    [
                        {"role": "system", "content": "把以下多条结论合并成一句连贯、无重复、结论先行的中文结论，只输出结论本身。"},
                        {"role": "user", "content": "\n".join(c["conclusion"] for c in cards)},
                    ],
                    model=model_for("summarize"), temperature=0.2)
            trace.step("summarize", output_summary=gen.content[:160], duration_ms=t.ms, token_usage=gen.total_tokens)
            card = {
                "conclusion": gen.content.strip(),
                "evidence": [e for c in cards for e in c["evidence"]],
                "steps": [s for c in cards for s in c["steps"]],
            }
            draft = render_card(card)
        else:
            draft = "这个问题我先帮你转接人工技术支持，请稍候。"
        return {"draft_answer": draft, "card": card}

    async def security_node(state: AgentState) -> dict:
        from app.guardrail import desensitize
        with timer() as t:
            res = security.review_output(state.get("draft_answer", ""))
            card = state.get("card")
            clean_card = desensitize.desensitize_obj(card) if card else None
        trace.step("security", output_summary=f"脱敏类型={res.sensitive_found}", duration_ms=t.ms)
        return {"final_answer": res.clean_text, "card": clean_card}

    g = StateGraph(AgentState)
    g.add_node("load_context", load_context)
    g.add_node("intent", intent_node)
    g.add_node("clarify", clarify_node)
    g.add_node("specialists", specialists_node)
    g.add_node("ticket", ticket_node)
    g.add_node("summarize", summarize_node)
    g.add_node("security", security_node)

    g.add_edge(START, "load_context")
    g.add_edge("load_context", "intent")
    g.add_conditional_edges("intent", after_intent, {"clarify": "clarify", "specialists": "specialists"})
    g.add_edge("clarify", END)
    g.add_edge("specialists", "ticket")
    g.add_edge("ticket", "summarize")
    g.add_edge("summarize", "security")
    g.add_edge("security", END)
    return g.compile()


async def run(
    *, query: str, tenant_id: str, user_id: str, conversation_id: str, is_internal: bool = False
) -> dict:
    """执行一次完整编排，返回结果并持久化链路与记忆。"""
    trace = TraceCollector(tenant_id=tenant_id, conversation_id=conversation_id)
    ctx = ToolContext(tenant_id=tenant_id, trace_id=trace.trace_id, is_internal=is_internal)

    # 语义缓存：命中热点问题则跳过完整链路
    with timer() as ct:
        cached, query_emb = await semantic_cache.get(tenant_id, query)
    if cached:
        trace.step("semantic_cache", input_summary=query,
                   output_summary=f"命中 similarity={cached['similarity']}", duration_ms=ct.ms)
        await session.append_message(conversation_id, "user", query)
        await session.append_message(conversation_id, "assistant", cached["answer"])
        await trace.persist()
        return {
            "answer": cached["answer"], "intent": cached["intent"], "confidence": 1.0,
            "citations": cached["citations"], "card": cached.get("card"),
            "need_human": False, "ticket_id": None,
            "trace_id": trace.trace_id, "total_tokens": 0, "entities": {},
            "need_clarify": False, "from_cache": True,
        }

    graph = build_graph(ctx, trace)

    init: AgentState = {
        "tenant_id": tenant_id, "user_id": user_id, "conversation_id": conversation_id,
        "is_internal": is_internal, "query": query,
    }
    try:
        final = await graph.ainvoke(init)
    except Exception as e:  # noqa: BLE001  管线级兜底：规则回复 + 自动建单转人工
        trace.step("fallback", input_summary=query, status="error", error=f"{type(e).__name__}: {e}")
        tk = await ticket.create_from_context(
            query=query, intent="ticket", entities={}, ai_diagnosis="",
            evidence={"pipeline_error": f"{type(e).__name__}: {e}"}, ctx=ctx,
            user_id=user_id, conversation_id=conversation_id)
        await trace.persist()
        return {
            "answer": f"{fallback.rule_reply(None)}（工单号 {tk.ticket_id}）",
            "intent": None, "confidence": 0.0, "citations": [], "need_human": True,
            "ticket_id": tk.ticket_id, "trace_id": trace.trace_id,
            "total_tokens": trace.total_tokens, "entities": {}, "need_clarify": False,
        }

    # 建单友好提示统一在此拼接（最终状态稳定含 ticket_message，避免节点可见性时序问题）
    answer = final.get("final_answer", "")
    ticket_message = final.get("ticket_message")
    if ticket_message and ticket_message not in answer:
        answer = f"{answer}\n\n{ticket_message}"

    result = {
        "answer": answer,
        "intent": final.get("intent"),
        "confidence": final.get("confidence"),
        "citations": final.get("rag_citations", []),
        "card": final.get("card"),
        "need_human": final.get("need_human", False),
        "ticket_id": final.get("ticket_id"),
        "trace_id": trace.trace_id,
        "total_tokens": trace.total_tokens,
        "entities": final.get("entities", {}),
        "need_clarify": final.get("need_clarify", False),
        "from_cache": False,
    }

    # 记忆：写入本轮对话
    await session.append_message(conversation_id, "user", query)
    await session.append_message(conversation_id, "assistant", result["answer"])
    # 持久化链路
    await trace.persist()
    # 成本统计
    await cost.record(tenant_id, conversation_id, "mixed", trace.total_tokens)
    # 语义缓存：仅缓存通用文档问答结果
    if (
        final.get("intent") == "doc_qa"
        and not final.get("need_clarify")
        and not final.get("need_human")
        and result["answer"]
    ):
        await semantic_cache.put(tenant_id, query, result, query_emb)

    return result
