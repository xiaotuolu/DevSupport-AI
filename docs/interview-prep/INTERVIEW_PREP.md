# DevSupport-AI 面试复习指南（代码级硬事实版）

> 目标：把"背过的概念"转化为"实现者才知道的细节"。面试官问"实现了多少个工具"这类问题时，
> 你要能脱口而出数字、名字、参数值，并能指向具体文件。

---

## 一、硬事实速查表（先背这个）

### 1. 总体规模

| 项 | 数值 |
| --- | --- |
| 后端源码 | 约 3500 行 Python（app/ 下），全项目含前端约 4800 行 |
| 工具总数 | **11 个**（8 个常规 + 3 个高风险占位） |
| Agent（严格口径：用了 LLM 才算） | **4 个**：IntentRouter（意图识别）+ DocRAG（文档问答）+ APIDiagnostic（报错诊断）+ Billing（账单解释）。注意：项目 README 里的 "TicketAgent / SecurityAgent" 没用 LLM，严格说不是 agent，是普通规则节点（详见 Q14） |
| 编排器 | Supervisor —— **规则编排器，不是 agent**：靠静态 ROUTE_MAP（意图→agent 列表）调度，不用 LLM 决策 |
| LangGraph 节点 | **7 个**。LLM 节点：intent、specialists（内部并发跑 DocRAG / APIDiagnostic / Billing 三个 agent）；条件 LLM 节点：summarize（多 card 合并时才用 LLM）；纯规则节点：load_context、clarify、ticket、security |
| 意图类别 | **7 种** |
| 抽取实体 | **9 种** |
| MySQL 表 | **19 张**；Milvus collection **1 个**（`knowledge_chunk`） |
| 知识库文档 | 5 篇 Markdown，约 3700 字 |
| 脱敏类型 | **8 类**，三层脱敏 |
| 兜底阶梯 | **7 级** |

### 2. 十一个工具（必须能逐个说出名字和用途）

| # | 工具名 | 用途 | 关键入参 |
| --- | --- | --- | --- |
| 1 | `query_call_log` | 按 request_id 查单次调用日志（诊断第一步） | request_id（必填） |
| 2 | `query_apikey_status` | 查 API Key 状态（401 诊断） | app_id 或 api_key_id |
| 3 | `query_recent_call_stats` | 统计近 N 分钟调用分布（429 诊断） | endpoint、minutes |
| 4 | `query_plan` | 查租户套餐（QPS/配额/单价） | 无 |
| 5 | `query_usage` | 查某月调用量与超额量 | month（YYYY-MM） |
| 6 | `query_bill` | 查某月账单与费用构成 | month |
| 7 | `create_ticket` | 创建工单（**唯一写操作**） | title/category/summary/priority(P0-P3)/evidence/ai_diagnosis |
| 8 | `query_ticket` | 查工单状态（已注册但当前无 agent/节点调用，预留） | ticket_id |
| 9 | `reset_api_key` | 高风险占位（`high_risk=True`，实际被拦截） | — |
| 10 | `change_plan` | 高风险占位 | — |
| 11 | `refund` | 高风险占位 | — |

工具防护参数：**超时 3.0 秒**（`asyncio.wait_for`）、**重试 1 次**（共 2 次尝试、无退避）、
每次调用写 `tool_call_log` 审计表（入参脱敏后截断 **1000** 字符、结果截断 **1500** 字符）。

### 3. 七种意图与路由表（ROUTE_MAP）

| 意图 | 含义 | 路由目标（agent / 节点） |
| --- | --- | --- |
| `doc_qa` | 文档/概念/用法类问题 | doc_rag |
| `api_error` | 具体一次调用报错 | api_diagnostic + doc_rag |
| `rate_limit` | 429/限流（复合问题） | api_diagnostic + billing + doc_rag |
| `billing` | 套餐/账单/用量 | billing + doc_rag |
| `data_quality` | 数据为空/不一致 | api_diagnostic + doc_rag |
| `ticket` | 明确要求人工/投诉 | ticket |
| `chitchat` | 闲聊 | 空路由，小模型直接回应 |

### 4. 九种实体

`request_id`、`error_code`、`http_status`、`endpoint`、`app_id`、`month`、`webhook_event_id`、`invoice_id`、`ticket_id`

### 5. 关键参数数字表（被追问时的弹药）

| 参数 | 值 | 位置 |
| --- | --- | --- |
| 意图澄清阈值 | confidence < **0.6** | config.py `intent_confidence_threshold` |
| 语义缓存相似度阈值 | 余弦 ≥ **0.95** | `semantic_cache_sim_threshold` |
| 语义缓存容量 | 每租户 **200 条**（LPUSH+LTRIM，无 TTL） | semantic_cache.py |
| 路由缓存 TTL | **24 小时**，key=MD5(归一化query) | route_cache.py |
| 历史消息窗口 | **20 条**（Redis List + LTRIM） | memory/session.py |
| 实体记忆 TTL | **6 小时** | memory/session.py |
| Embedding | text-embedding-v3，**1024 维**，每批 10 条 | llm/client.py |
| 切片 | 按 H2 章节切，长章节 **600 字符**窗口 + **80 字符**重叠 | rag/ingest.py |
| Milvus 索引 | **HNSW**（M=16, efConstruction=200），**COSINE**，检索 ef=64 | rag/store.py |
| 混合检索召回 | 向量、BM25 **各 top 20** | rag/retriever.py |
| RRF 融合 | `score = Σ 1/(k+rank+1)`，**k=60** | rag/retriever.py |
| Rerank | **gte-rerank-v2**，取 **top 5**（dashscope 原生 SDK + `asyncio.to_thread`） | rag/reranker.py |
| RAG 命中判定 | 向量余弦 ≥ **0.45** **或** rerank 分 ≥ **0.3**（双信号 OR） | config.py |
| 上下文压缩 | 过滤 rerank < **0.05**，字符预算 **1800**，纯规则不用 LLM | rag/compressor.py |
| LLM 重试 | tenacity：**3 次**、指数退避 multiplier=0.5 上限 4s、仅 4 类瞬时错误 | llm/client.py |
| 工具超时/重试 | **3.0s** / 重试 **1** 次 | config.py + registry.py |
| JWT | **HS256**、有效期 **720 分钟**（12h）、bcrypt（截断 72 字节） | security.py |
| SSE | **18 字符/块**、每块 sleep **0.02s**（伪流式） | api/chat.py |
| 模型分层 | 小模型 **qwen-turbo**（intent/clarify/chitchat/route）；大模型 **qwen-plus**（diagnose/summarize/rag_generate/billing_explain） | llm/router.py |
| 评估集 | **15 条**主用例 + **8 条**脱敏用例，规则比对、**6 项指标**、无 LLM judge | eval/run_eval.py |
| 压测 | 自研 asyncio 脚本，**并发 4 × 重复 2**，缓存前后对比 | benchmark/loadtest.py |
| 时间锚点 | 过期判定等硬编码 `datetime(2026, 6, 15)`（演示数据可复现，不依赖系统时间） | tools/apikey.py 等 |

---

## 二、代码阅读优先级清单

### P0：必读（约 900 行，面试核心，建议 3-4 小时精读）

| 顺序 | 文件 | 行数 | 读什么 |
| --- | --- | --- | --- |
| 1 | `agents/state.py` | 38 | AgentState 全部字段（TypedDict, total=False，无 reducer）。先建立状态心智模型 |
| 2 | `agents/supervisor.py` | 318 | **全项目最重要的文件**。①`build_graph`：7 节点 + 条件边 `after_intent`；②`specialists_node` 里 `asyncio.gather` 并行 + `_run_agent` 异常隔离；③`run()` 入口：语义缓存前置 → 构图 → ainvoke → 管线级兜底（fallback + 自动建单）→ 缓存回写条件 |
| 3 | `tools/registry.py` | 114 | ToolSpec/ToolContext/REGISTRY 三件套；`execute()` 里的超时、重试、高风险拦截、脱敏日志。面试官问"工具怎么实现的"就答这里 |
| 4 | `agents/intent_router.py` | 112 | 7 意图 ROUTE_MAP、9 实体、LLM 分类(temperature=0) + 4 条正则兜底补抽实体、JSON 稳健解析 |
| 5 | `agents/api_diagnostic.py` | 125 | 最复杂的专业 agent（LLM）：查日志回填实体 → 三路证据 `asyncio.gather` 并行（Key 状态/限流统计/文档）→ 错误码热路径 `_error_doc_fast` 直查 MySQL 跳过 RAG → LLM 组装诊断卡片 |
| 6 | `rag/retriever.py` | 83 | 混合检索：向量 top20 + BM25 top20 → content 去重 → RRF k=60 融合；BM25 内存索引懒加载 |

### P1：重要支撑（约 900 行，建议 3 小时）

| 文件 | 行数 | 读什么 |
| --- | --- | --- |
| `rag/ingest.py` + `rag/store.py` | 141+127 | 切片策略（H2 章节/600字/80重叠/错误码正则抽取）、Milvus schema、HNSW 参数 |
| `agents/doc_rag.py` | 100 | RAG 六步流水线：查询改写→混合检索→rerank→命中判定→压缩→带引用生成；`NO_HIT_MESSAGE` 防幻觉 |
| `rag/reranker.py` + `rag/compressor.py` | 20+42 | rerank 调用方式；压缩的两个参数（0.05 / 1800） |
| `guardrail/desensitize.py` | 95 | 8 类正则逐个看一遍（尤其 api_key 保前7后4、环视断言替代 `\b` 的设计） |
| `cache/semantic_cache.py` + `cache/route_cache.py` | 70+32 | 语义缓存的 Redis List 结构、余弦相似度、200 条上限；路由缓存 MD5 key |
| `memory/session.py` | 50 | 历史窗口 LTRIM -20 -1、实体合并非空覆盖 |
| `llm/client.py` + `llm/router.py` | 144+15 | OpenAI 兼容模式调 DashScope、tenacity 配置、模型分层 |
| `tools/` 其余四个文件 | ~370 | 每个工具查哪张表；`query_recent_call_stats` 的"429 锚点"算法 |
| `agents/billing.py` + `ticket.py` + `security.py` | 83+63+22 | Billing agent（LLM）的 17 个高风险关键词；ticket 节点（非 agent）的 CATEGORY_MAP 优先级映射；security 节点（非 agent）纯规则脱敏 |

### P2：了解即可（约 1300 行，建议 1.5 小时扫一遍）

| 文件 | 看什么 |
| --- | --- |
| `api/chat.py` | SSE 三种事件（meta/token/done）、人工模式分支、消息落库 meta 字段 |
| `api/auth.py` + `security.py` + `deps.py` | JWT 签发校验、bcrypt、`get_current_user` 回查库、`require_internal` |
| `models.py` | 19 张表过一遍名字和用途（能说出 8-10 张即可） |
| `observability/trace.py` + `cost.py` | TraceCollector.step 字段、timer 上下文管理器、persist 独立会话 |
| `api/workbench.py` | 工单状态机 6 态、takeover/suggest_reply/reply 人工接管三接口 |
| `eval/run_eval.py` + `benchmark/loadtest.py` | 6 项指标定义；压测的缓存前后对比设计 |
| `guardrail/fallback.py` | 7 级兜底阶梯（文件头注释，直接背） |
| 前端 `src/pages/Chat.tsx`、`components/TraceFlow.tsx` | SSE 消费、React Flow 渲染 trace（被问前端时说得出即可） |

---

## 三、端到端链路默写版（必须能流畅讲出来）

以「**我调用实名认证接口一直返回 401，request_id 是 req_20260615_8842**」为例：

```
1. POST /api/chat（SSE）→ JWT 校验（HS256，decode 后回查 User 表拿最新 role/tenant_id）
2. 获取/创建会话（校验租户归属防越权）
3. supervisor.run()：
   3.1 先查语义缓存（Redis List，余弦≥0.95）→ 未命中
   3.2 build_graph 按请求构建 LangGraph 图（闭包捕获 ToolContext + TraceCollector）
   3.3 load_context：从 Redis 取最近 20 条历史 + 实体记忆
   3.4 intent 节点：
       - 首轮先查路由缓存（MD5 key，TTL 24h）；未命中 → qwen-turbo 分类（temperature=0）
       - 输出：intent=api_error，实体 {request_id, http_status:401, endpoint}
       - 4 条正则兜底补抽 LLM 漏掉的实体（setdefault，LLM 优先）
       - 新实体与记忆合并（非空才覆盖），写回 Redis（TTL 6h）
       - 澄清判定：api_error 但缺 request_id 和 error_code → 追问；confidence<0.6 → 追问
   3.5 条件边 after_intent → specialists 节点：
       - route=[api_diagnostic, doc_rag]，asyncio.gather 并行执行
       - 但 route 里有 api_diagnostic 时 doc_rag 不单独跑（诊断内部已含文档检索，避免重复 RAG）
       - APIDiagnosticAgent：
         ① execute("query_call_log") 查日志 → 回填 error_code/app_id
         ② 三路并行 gather：Key 状态(仅401类错误码) / 限流统计 / 文档支撑
         ③ 文档路热路径：error_code 直查 MySQL error_code 表，命中跳过 RAG
         ④ qwen-plus 组装诊断卡片 {conclusion, evidence, steps, need_ticket}
       - 单 agent 异常被 _run_agent try/except 隔离，不炸管线
   3.6 ticket 节点：need_ticket 或 need_human 时经 create_ticket 工具建单
       （CATEGORY_MAP：api_error→"API报错"P1），诊断与证据随单落库（各截断2000字）
   3.7 summarize 节点：单 card 直接 render_card；多 card 用大模型合并结论
   3.8 security 节点（最后一个节点，串行保证审查必经）：
       review_output 脱敏 draft_answer + desensitize_obj 递归脱敏 card
   3.9 管线级兜底：ainvoke 抛异常 → 规则话术 + 自动建单转人工
   3.10 trace.persist() 落 agent_trace 表 + cost.record 落 token_usage 表
   3.11 语义缓存回写：仅 doc_qa 且未澄清未转人工才写
4. SSE 回传：meta（intent/trace_id）→ token 块（18字符/块伪流式）→ done（卡片/引用/工单号）
5. 前端渲染诊断卡片 + 引用 Tag + React Flow 链路图
```

**RAG 链路单独默写版**（doc_qa 问题）：

```
查询改写（有历史时用 qwen-turbo 补全指代，取最近4轮）
→ 混合检索：Milvus 向量 top20（HNSW/COSINE/ef=64） + BM25 top20（rank_bm25+jieba，内存索引）
→ 按 content 去重 → RRF 融合（score=Σ1/(60+rank+1)）
→ gte-rerank-v2 精排取 top5
→ 命中判定：向量余弦≥0.45 或 rerank≥0.3（OR，双信号互补）
→ 上下文压缩：丢 rerank<0.05 的片段，1800 字符预算，至少保 1 条
→ build_context：[i]《文档标题》-章节 编号注入
→ qwen-plus 生成 JSON 卡片（temperature=0.2，prompt 强制"只能基于参考资料"）
→ 未命中返回 NO_HIT_MESSAGE（主动承认没找到、建议转人工，防幻觉）
```

---

## 四、高频追问与代码级答案要点

**Q1：你们实现了多少个工具？怎么管理的？**
11 个：8 个常规查询/建单工具 + 3 个高风险占位工具。自研注册表管理（`ToolSpec` + 全局 `REGISTRY` 字典），
没用 LangChain 的 `@tool`。好处是超时(3s)/重试/结果脱敏/高危拦截这些横切关注点统一收口在 `execute()`，
一次实现全局生效。每个工具是 `async def f(args: dict, ctx: ToolContext) -> dict`，
schema 是手写 JSON Schema dict，`openai_tools()` 可转成 OpenAI function calling 格式。

**Q2：工具是 LLM 自主选择调用吗（function calling）？**
不是。当前是**确定性编排**：意图路由 → 专业 agent → 代码里按条件硬编码调用工具。
理由：客服场景可枚举、要求可观测可复现，让 LLM 自由选工具会引入不确定性和高风险操作风险；
function calling 能力在 LLM client 里已预留（支持 tools 参数和 tool_calls 解析），是可演进的扩展位。
（这是设计决策，要讲得理直气壮，别当成缺陷。）

**Q3：多 Agent 怎么并行？用 LangGraph 的 Send API 吗？**
不是 Send。图层面是串行的 7 节点 DAG（串行是为了保证 security 审查节点必经），
并行发生在 `specialists` 节点内部：按 route 构建协程列表后 `asyncio.gather` 一次性并发。
每个 agent 包在 `_run_agent` 里 try/except，单个失败只记 error trace 不拖垮整体。
APIDiagnostic 内部还有第二层 gather（三路证据并行）。

**Q4：为什么混合检索？RRF 公式？**
API 文档里大量错误码/接口名/参数名是精确关键词，BM25 更稳；自然语言提问需要向量语义补召回。
RRF：`score(d)=Σ 1/(k+rank+1)`，k=60，rank 从 0 开始；对分数尺度不敏感、无需调权。

**Q5：RAG 怎么防幻觉？**
四道：① prompt 强制"只能基于参考资料，不得编造"；② 命中阈值判定（向量≥0.45 或 rerank≥0.3），
不命中直接返回 NO_HIT_MESSAGE 并建议建工单；③ 上下文压缩丢掉 rerank<0.05 的噪声片段；
④ 引用以结构化元数据返回（不靠 LLM 在正文写 [n]），前端可点击溯源。

**Q6：缓存分几层？**
三层：① 路由缓存——意图分类结果，MD5 key、TTL 24h，仅首轮用（多轮下同 query 意图可能变）；
② 语义缓存——doc_qa 最终答案，query 向量化后与 Redis List 里 ≤200 条条目算余弦，≥0.95 命中，
命中直接返回 `total_tokens=0`，只回写"干净的" doc_qa 结果（不缓存租户相关的诊断/账单）；
③ 错误码热路径——已知 error_code 直查 MySQL error_code 表，跳过整个 embed/rerank/generate。

**Q7：敏感信息怎么防护？**
三层脱敏 + 数据源头不落库：用户消息/人工回复入库前脱敏；工具调用的入参(截断1000)和结果(截断1500)
脱敏后写审计表；最终回复在 security 节点强制脱敏（文本 + 递归脱敏卡片）。8 类正则：
api_key（保前7后4）、secret、Bearer token、身份证、银行卡、手机号、邮箱、签名。
数据库 api_key 表只存 `key_masked`，原始密钥根本不落库。
正则细节：数字类用 `(?<!\d)/(?!\d)` 环视断言替代 `\b`（中文紧邻时 `\b` 失效）。

**Q8：高风险操作（退款/改价/重置Key）怎么处理？**
四道闸：① `openai_tools()` 默认不输出 high_risk 工具，LLM 看不到；② `execute()` 里
非内部角色调用直接拒绝；③ 工具函数本身是占位符 `_high_risk_blocked`；④ Billing agent 用
17 个关键词（退款/改价/降级…）识别高风险意图，只解释不执行、置 need_human 转人工。

**Q9：系统挂了怎么办？（容错设计）**
7 级兜底阶梯：tenacity 重试 LLM 瞬时错误 → 单 agent 异常隔离 → RAG 无命中提示 →
低置信澄清 → 工具失败返回 {ok:False} 降级 → 高风险/低置信转人工建单 →
整条管线异常时规则话术 + 自动建单（evidence 记 pipeline_error）。

**Q10：可观测怎么做的？**
每个节点用 `TraceCollector.step()` 记录：节点名、step_order、输入输出摘要（各截断500字）、
状态、duration_ms（timer 上下文管理器 perf_counter）、token_usage、命中文档列表。
落 MySQL agent_trace 表，前端 React Flow 画链路图。token 成本按租户聚合到 token_usage 表。

**Q11：多租户怎么隔离？**
tenant_id 从 JWT 解析后回查 User 表获得（不信请求体）；ToolContext 带着 tenant_id 进每个工具，
工具内部过滤 `tenant_id == ctx.tenant_id`（内部支持角色 is_internal 可跨租户）；
会话复用时校验归属；语义缓存按租户分桶 `semcache:{tenant_id}`。

**Q12：评估怎么做的？**
离线评估集 15 条主用例 + 8 条脱敏用例，端到端真跑 supervisor.run()（先清缓存），
规则比对 6 项指标：意图准确率、实体准确率、引用率、转人工准确率、澄清准确率、脱敏准确率。
Badcase 自动归因（意图识别/转人工判定）。没用 LLM judge——指标都是可判定的结构化断言。

**Q13：SSE 是真流式吗？**
诚实答：当前是"结果级流式"——编排完整跑完后按 18 字符/块、20ms 间隔模拟打字机推送。
LLM client 里有真正的 chat_stream（逐 token），是可升级的演进点。这样答比硬说真流式安全。

**Q14：工单/安全也算 agent 吗？它们没用到 LLM 吧？（高频追问）**
你的判断是对的，直接按严格口径回答（"有 LLM 参与决策的才算 agent"）：
① **系统里真正的 agent 只有 4 个**：IntentRouter（LLM 意图分类）、DocRAG、APIDiagnostic、
Billing（LLM 推理生成）。工单（ticket.py：CATEGORY_MAP 规则 + create_ticket 工具调用）和
安全审查（security.py：纯正则脱敏，无 LLM 无 IO）**没有 LLM，是普通规则节点**——
README 里写的 "TicketAgent / SecurityAgent" 只是按业务职责的宽口径命名，不严谨。
② 图结构上它俩**就是独立的 LangGraph 节点**（ticket_node / security_node）；
反而三个用了 LLM 的 agent 不是独立节点，是 `specialists` 节点内 gather 并发的协程。
Supervisor 也不算 agent——不用 LLM 决策，靠静态 ROUTE_MAP（意图→agent 列表）调度，
是规则编排器，LLM 判断全部前置到了意图分类一步。
③ 设计拔高（加分）：按 Anthropic "workflow vs agent" 划分，本项目是 **workflow 模式**——
LLM 在预定义代码路径的固定环节运行，而非 LLM 自主决定流程的全自主 agent。
客服场景可枚举、要求可预测/可观测/安全（高风险操作绝不能交给 LLM 自由决策），
这是刻意选择；function calling 能力已在 LLM client 预留，是可演进方向。

---

## 五、容易被问穿的点（提前准备，主动承认 > 被动暴露）

| 坑 | 实际情况 | 应对话术 |
| --- | --- | --- |
| "知识库有几篇文档？" | **只有 5 篇**（01/04/06/07/08），README 说的 8 篇里缺 02鉴权、03错误码、05限流 | "演示语料 5 篇约 3700 字；鉴权和错误码知识走 MySQL error_code 表的结构化查询覆盖，不依赖 RAG，这是刻意的——错误码需要精确匹配而非语义近似" |
| "有单元测试吗？" | 没有 tests/，只有 eval 评估集 + benchmark | "质量保障主要靠端到端评估集（6 项指标）和压测，单测确实是待补项" |
| "压测并发多少？" | 只有 4 并发 × 2 轮，且不走 HTTP 直调 supervisor.run | "重点在缓存前后对比和阶段耗时分解，不是极限压测" |
| "token 成本算钱吗？" | 只记用量（token_usage 表，model 写 "mixed"），无 LLM 单价配置 | 如实说，补充"金额计费是 API 调用维度的 plan.price_per_call，不是 token 计价" |
| `query_recent_call_stats` | schema 描述说默认 60 分钟，代码实际默认 240 | 这是个 schema 与实现不一致的小瑕疵，被问到就说调用方都显式传参（api_diagnostic 传 60） |
| BM25 索引 | 纯内存、无持久化，ingest 后没调 reset_bm25 | "API 进程首次查询时从 Milvus 拉全量切片懒加载重建，语料小（几百个 chunk）重建成本低" |
| 时间锚点 | 过期判定硬编码 datetime(2026,6,15) | 主动讲设计意图："演示数据锚定固定基准时间，保证过期判定和限流统计可复现、不受系统时间漂移影响，生产替换为 now() 即可" |
| `openai_tools()` 和 `query_ticket` | 都没有调用方 | "预留能力，产品链路走确定性编排" |
| 图有 checkpointer 吗？ | 没有，状态纯内存、无 reducer，覆盖式更新；持久化在图外（session.append_message / trace.persist） | 如实说，并解释为什么够用（单轮请求内完成，无需断点续跑） |
| "ticket/security 没 LLM 算什么 agent？" | 确实没用 LLM，图里就是普通规则节点；严格口径下系统只有 4 个 agent；Supervisor 也是静态路由表的规则编排器 | 直接按严格口径答（Q14）：4 个 agent + 7 个节点，README 的命名是宽口径不严谨 → 落到"workflow 式确定性编排是刻意设计" |

---

## 六、复习时间安排建议

**如果有 1 天（6-8 小时）：**
- 上午（3.5h）：精读 P0 六个文件，边读边对照本文第三节的链路默写版验证理解
- 下午（3h）：P1 文件 + 背数字表（第二节表 5）
- 晚上（1.5h）：P2 扫一遍 + 自测：合上文档，口头回答第四节 14 个问题

**如果只有 2 小时：**
只读 `supervisor.py` + `registry.py`（共 430 行），背熟：
11 个工具名、7 个意图、并行用 asyncio.gather、RRF k=60、缓存阈值 0.95、
命中阈值 0.45/0.3、超时 3s、脱敏 8 类、澄清阈值 0.6。这 9 个数字能覆盖最高频的追问。

**自测标准**：能不看资料默写出第三节的端到端链路，且每个环节至少带一个具体数字或函数名。
