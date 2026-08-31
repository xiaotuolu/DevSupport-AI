# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""种子数据：真实写入 MySQL（幂等，可重复执行）。

包含：
- 固定"剧本数据"：用于 4 个黄金场景可复现演示（如 401 的 req_20260615_8842）。
- 背景数据：近 30 天随机调用日志，让数据更真实。

用法（backend 目录下）：python -m scripts.seed_data
"""

import random
from datetime import datetime, timedelta

from sqlalchemy import delete

from app.db import SyncSessionLocal
from app.models import (
    ApiCallLog,
    ApiEndpoint,
    ApiKey,
    App,
    ErrorCode,
    Invoice,
    Plan,
    Tenant,
    UsageRecord,
    User,
)
from app.security import hash_password

random.seed(20260615)
NOW = datetime(2026, 6, 15, 18, 0, 0)

# ---------------- 套餐 ----------------
PLANS = [
    dict(id="plan_free", name="免费版", qps_limit=5, monthly_quota=10000,
         price_per_call=0.010, overage_price_per_call=0.020),
    dict(id="plan_basic", name="基础版", qps_limit=20, monthly_quota=100000,
         price_per_call=0.008, overage_price_per_call=0.015),
    dict(id="plan_pro", name="专业版", qps_limit=50, monthly_quota=500000,
         price_per_call=0.006, overage_price_per_call=0.012),
    dict(id="plan_enterprise", name="企业版", qps_limit=200, monthly_quota=2000000,
         price_per_call=0.004, overage_price_per_call=0.008),
]

# ---------------- 租户 ----------------
TENANTS = [
    dict(id="t_acme", name="Acme 数据科技", plan_id="plan_pro"),
    dict(id="t_globex", name="Globex 金融", plan_id="plan_enterprise"),
    dict(id="t_initech", name="Initech 物流", plan_id="plan_basic"),
    dict(id="t_platform", name="DevSupport 平台（内部）", plan_id=None),
]

# ---------------- 用户（密码统一 password123） ----------------
PWD = "password123"
USERS = [
    dict(id="u_acme_dev", tenant_id="t_acme", username="dev_acme", role="customer_dev", display_name="Acme 开发者"),
    dict(id="u_acme_admin", tenant_id="t_acme", username="admin_acme", role="customer_admin", display_name="Acme 管理员"),
    dict(id="u_globex_dev", tenant_id="t_globex", username="dev_globex", role="customer_dev", display_name="Globex 开发者"),
    dict(id="u_globex_admin", tenant_id="t_globex", username="admin_globex", role="customer_admin", display_name="Globex 管理员"),
    dict(id="u_initech_dev", tenant_id="t_initech", username="dev_initech", role="customer_dev", display_name="Initech 开发者"),
    dict(id="u_support1", tenant_id="t_platform", username="support1", role="support", display_name="技术支持-小王"),
    dict(id="u_support2", tenant_id="t_platform", username="support2", role="support", display_name="技术支持-小李"),
    dict(id="u_admin", tenant_id="t_platform", username="admin", role="admin", display_name="系统管理员"),
]

# ---------------- 应用与密钥 ----------------
APPS = [
    dict(id="app_acme", tenant_id="t_acme", name="Acme 生产应用"),
    dict(id="app_globex", tenant_id="t_globex", name="Globex 风控应用"),
    dict(id="app_initech", tenant_id="t_initech", name="Initech 物流应用"),
]
API_KEYS = [
    # Acme 一把已过期的 key（401 场景）+ 一把有效 key
    dict(id="key_acme_expired", app_id="app_acme", tenant_id="t_acme",
         key_masked="ak_live_****8a2f", status="EXPIRED", expire_at=datetime(2026, 6, 10)),
    dict(id="key_acme_active", app_id="app_acme", tenant_id="t_acme",
         key_masked="ak_live_****3c7d", status="ACTIVE", expire_at=datetime(2027, 1, 1)),
    dict(id="key_globex_active", app_id="app_globex", tenant_id="t_globex",
         key_masked="ak_live_****b19e", status="ACTIVE", expire_at=datetime(2027, 1, 1)),
    dict(id="key_initech_active", app_id="app_initech", tenant_id="t_initech",
         key_masked="ak_live_****6d40", status="ACTIVE", expire_at=datetime(2027, 1, 1)),
]

# ---------------- 接口 ----------------
ENDPOINTS = [
    dict(id="ep_idcard", product="实名认证", path="/v1/idcard/verify", name="身份证实名核验"),
    dict(id="ep_company", product="数据查询", path="/v1/company/query", name="企业信息查询"),
    dict(id="ep_risk", product="风控评分", path="/v1/risk/score", name="风控评分"),
    dict(id="ep_bankcard", product="实名认证", path="/v1/bankcard/verify", name="银行卡核验"),
]
ENDPOINT_PATHS = [e["path"] for e in ENDPOINTS]

# ---------------- 错误码手册（与知识库《错误码手册》一致） ----------------
ERROR_CODES = [
    dict(code="AUTH_KEY_EXPIRED", name="API Key 已过期", http_status=401,
         cause="请求使用的 API Key 已超过有效期。",
         fix_steps="1. 登录控制台查看 Key 状态与过期时间；2. 重新生成 API Key；3. 更新服务端配置后重试。"),
    dict(code="AUTH_KEY_INVALID", name="API Key 无效", http_status=401,
         cause="API Key 不存在、被禁用或格式错误。",
         fix_steps="1. 核对 Key 是否复制完整；2. 确认 Key 未被禁用；3. 使用控制台有效 Key 重试。"),
    dict(code="SIGN_INVALID", name="签名错误", http_status=401,
         cause="请求签名与服务端计算不一致，常见于参数排序、时间戳或密钥错误。",
         fix_steps="1. 按文档对参数字典序排序拼接；2. 确认使用正确 Secret；3. 校验时间戳在 5 分钟内；4. 重新计算签名。"),
    dict(code="PERMISSION_DENIED", name="权限不足", http_status=403,
         cause="当前应用无该接口或资源的访问权限。",
         fix_steps="1. 确认应用已开通该 API 产品；2. 联系管理员授权；3. 重试。"),
    dict(code="PRODUCT_NOT_ENABLED", name="接口未开通", http_status=403,
         cause="该 API 产品尚未为应用开通。",
         fix_steps="1. 控制台开通对应 API 产品；2. 等待生效后重试。"),
    dict(code="IP_NOT_ALLOWED", name="IP 不在白名单", http_status=403,
         cause="请求来源 IP 不在应用配置的白名单内。",
         fix_steps="1. 控制台将服务器出口 IP 加入白名单；2. 等待生效后重试。"),
    dict(code="NOT_FOUND", name="接口不存在", http_status=404,
         cause="请求路径错误或接口已下线。",
         fix_steps="1. 核对接口路径与版本；2. 参考最新文档。"),
    dict(code="REQUEST_TIMEOUT", name="请求超时", http_status=408,
         cause="请求处理超时，可能为网络或上游慢。",
         fix_steps="1. 增大客户端超时时间；2. 重试；3. 持续出现请提工单。"),
    dict(code="RATE_LIMIT_EXCEEDED", name="QPS 超限", http_status=429,
         cause="单位时间请求数超过套餐 QPS 限制。",
         fix_steps="1. 客户端做本地限速；2. 采用指数退避重试；3. 错峰调用；4. 如需更高并发请升级套餐。"),
    dict(code="QUOTA_EXCEEDED", name="调用量超额", http_status=429,
         cause="本月调用量已超出套餐配额。",
         fix_steps="1. 查看本月用量；2. 升级套餐或购买加量包；3. 次月自动恢复。"),
    dict(code="INTERNAL_ERROR", name="服务端错误", http_status=500,
         cause="服务端内部异常。",
         fix_steps="1. 稍后重试；2. 记录 request_id；3. 持续出现请提工单。"),
    dict(code="PARAM_MISSING", name="参数缺失", http_status=400,
         cause="缺少必填参数。",
         fix_steps="1. 对照文档补齐必填参数；2. 重试。"),
    dict(code="PARAM_INVALID", name="参数格式错误", http_status=400,
         cause="参数类型或格式不符合要求。",
         fix_steps="1. 核对参数类型与格式；2. 修正后重试。"),
    dict(code="BALANCE_NOT_ENOUGH", name="余额不足", http_status=402,
         cause="账户余额不足以完成本次计费调用。",
         fix_steps="1. 控制台充值；2. 充值后重试。"),
    dict(code="DATA_EMPTY", name="查询结果为空", http_status=200,
         cause="请求成功但未命中数据，可能为参数不匹配或数据未覆盖。",
         fix_steps="1. 核对查询参数；2. 确认数据覆盖范围；3. 如确认应有数据请提数据质量工单。"),
    dict(code="DATA_INCONSISTENT", name="数据不一致", http_status=200,
         cause="返回数据与预期来源存在差异，可能为更新延迟。",
         fix_steps="1. 查看数据更新时间；2. 提供对比样例提数据质量工单。"),
    dict(code="WEBHOOK_DELIVERY_FAILED", name="回调投递失败", http_status=200,
         cause="平台已发送回调但客户地址返回非 2xx 或不可达。",
         fix_steps="1. 确认回调地址可公网访问；2. 返回 200 表示已接收；3. 平台会按策略重试。"),
    dict(code="WEBHOOK_SIGN_INVALID", name="回调验签失败", http_status=200,
         cause="客户侧对回调验签失败。",
         fix_steps="1. 使用回调密钥按文档验签；2. 注意原始 body 不要被改写。"),
]


def _clear(session):
    for model in (ApiCallLog, ApiKey, App, ApiEndpoint, ErrorCode, Invoice,
                  UsageRecord, User, Tenant, Plan):
        session.execute(delete(model))


def _gen_background_logs() -> list[dict]:
    """近 30 天背景调用日志：多数 200，少量各类错误。"""
    rows = []
    tenants_apps = [("t_acme", "app_acme", "key_acme_active"),
                    ("t_globex", "app_globex", "key_globex_active"),
                    ("t_initech", "app_initech", "key_initech_active")]
    err_pool = ["PARAM_INVALID", "PARAM_MISSING", "RATE_LIMIT_EXCEEDED",
                "INTERNAL_ERROR", "SIGN_INVALID", "PERMISSION_DENIED"]
    seq = 0
    for day in range(30):
        ts_day = NOW - timedelta(days=day)
        for _ in range(random.randint(35, 50)):
            seq += 1
            tenant, app, key = random.choice(tenants_apps)
            endpoint = random.choice(ENDPOINT_PATHS)
            ts = ts_day.replace(hour=random.randint(0, 23), minute=random.randint(0, 59),
                                second=random.randint(0, 59))
            if random.random() < 0.85:
                status, err = 200, None
            else:
                err = random.choice(err_pool)
                status = next(e["http_status"] for e in ERROR_CODES if e["code"] == err)
            rid = f"req_{ts.strftime('%Y%m%d')}_{seq:04d}"
            rows.append(dict(request_id=rid, tenant_id=tenant, app_id=app, api_key_id=key,
                             endpoint=endpoint, http_status=status, error_code=err,
                             latency_ms=random.randint(40, 800),
                             client_ip=f"203.0.113.{random.randint(2, 250)}", created_at=ts))
    return rows


def _gen_scripted_logs() -> list[dict]:
    """固定剧本日志：4 个黄金场景可复现。"""
    rows = []
    # 场景①：401 鉴权失败（Key 过期）
    rows.append(dict(request_id="req_20260615_8842", tenant_id="t_acme", app_id="app_acme",
                     api_key_id="key_acme_expired", endpoint="/v1/idcard/verify",
                     http_status=401, error_code="AUTH_KEY_EXPIRED", latency_ms=35,
                     client_ip="203.0.113.10", created_at=datetime(2026, 6, 15, 14, 22, 0)))
    # 场景②：429 限流（Globex 风控接口下午突发大量 429）
    for i in range(18):
        ts = datetime(2026, 6, 15, 15, random.randint(0, 30), random.randint(0, 59))
        rows.append(dict(request_id=f"req_20260615_90{i:02d}", tenant_id="t_globex",
                         app_id="app_globex", api_key_id="key_globex_active",
                         endpoint="/v1/risk/score", http_status=429,
                         error_code="RATE_LIMIT_EXCEEDED", latency_ms=12,
                         client_ip="198.51.100.7", created_at=ts))
    # 场景⑤：数据质量（请求成功但客户认为数据不一致）
    rows.append(dict(request_id="req_20260614_5521", tenant_id="t_acme", app_id="app_acme",
                     api_key_id="key_acme_active", endpoint="/v1/company/query",
                     http_status=200, error_code=None, latency_ms=220,
                     client_ip="203.0.113.10", created_at=datetime(2026, 6, 14, 10, 5, 0)))
    # 附加：签名错误样例
    rows.append(dict(request_id="req_20260613_3302", tenant_id="t_initech", app_id="app_initech",
                     api_key_id="key_initech_active", endpoint="/v1/bankcard/verify",
                     http_status=401, error_code="SIGN_INVALID", latency_ms=28,
                     client_ip="192.0.2.55", created_at=datetime(2026, 6, 13, 9, 12, 0)))
    return rows


def _gen_usage_and_invoices():
    """用量与账单：t_acme 6 月环比大涨且产生超额（账单解释场景）。"""
    plan_by_tenant = {t["id"]: t["plan_id"] for t in TENANTS}
    plan_map = {p["id"]: p for p in PLANS}
    # (tenant, month, calls)
    usage_plan = [
        ("t_acme", "2026-04", 210000),
        ("t_acme", "2026-05", 215000),
        ("t_acme", "2026-06", 560000),   # 环比大涨，超过专业版 50万配额
        ("t_globex", "2026-05", 1500000),
        ("t_globex", "2026-06", 1620000),
        ("t_initech", "2026-05", 60000),
        ("t_initech", "2026-06", 72000),
    ]
    usage_rows, invoice_rows = [], []
    for tenant, month, calls in usage_plan:
        plan = plan_map[plan_by_tenant[tenant]]
        quota = plan["monthly_quota"]
        overage = max(0, calls - quota)
        base_calls = min(calls, quota)
        base_fee = round(base_calls * plan["price_per_call"], 2)
        overage_fee = round(overage * plan["overage_price_per_call"], 2)
        total = round(base_fee + overage_fee, 2)
        usage_rows.append(dict(tenant_id=tenant, month=month, call_count=calls,
                               overage_count=overage))
        invoice_rows.append(dict(id=f"inv_{tenant}_{month.replace('-', '')}", tenant_id=tenant,
                                 month=month,
                                 items=dict(plan=plan["name"], base_calls=base_calls,
                                            base_fee=base_fee, overage_calls=overage,
                                            overage_fee=overage_fee, total=total),
                                 amount=total, status="ISSUED"))
    return usage_rows, invoice_rows


def main() -> None:
    with SyncSessionLocal() as s:
        _clear(s)
        s.flush()
        # 按外键依赖顺序逐组 flush
        s.add_all([Plan(**p) for p in PLANS]); s.flush()
        s.add_all([Tenant(**t) for t in TENANTS]); s.flush()
        s.add_all([User(password_hash=hash_password(PWD), **u) for u in USERS]); s.flush()
        s.add_all([App(**a) for a in APPS]); s.flush()
        s.add_all([ApiKey(**k) for k in API_KEYS]); s.flush()
        s.add_all([ApiEndpoint(**e) for e in ENDPOINTS]); s.flush()
        s.add_all([ErrorCode(**e) for e in ERROR_CODES]); s.flush()

        logs = _gen_scripted_logs() + _gen_background_logs()
        s.add_all([ApiCallLog(**row) for row in logs]); s.flush()

        usage_rows, invoice_rows = _gen_usage_and_invoices()
        s.add_all([UsageRecord(**u) for u in usage_rows])
        s.add_all([Invoice(**inv) for inv in invoice_rows])

        s.commit()

        print(f"[seed] 套餐 {len(PLANS)}、租户 {len(TENANTS)}、用户 {len(USERS)}、"
              f"应用 {len(APPS)}、密钥 {len(API_KEYS)}、接口 {len(ENDPOINTS)}、"
              f"错误码 {len(ERROR_CODES)}")
        print(f"[seed] 调用日志 {len(logs)}（含剧本 {len(_gen_scripted_logs())}）、"
              f"用量 {len(usage_rows)}、账单 {len(invoice_rows)}")
        print("[seed] 完成。统一密码: password123")


if __name__ == "__main__":
    main()
