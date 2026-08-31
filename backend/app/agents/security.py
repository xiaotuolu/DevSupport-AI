# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""Security Agent：最终回复前的安全审查与脱敏（强制执行）。

- 对最终输出做敏感信息脱敏（API Key/Secret/Token/手机号/邮箱/身份证/签名）。
- 标注检测到的敏感类型，写入安全事件（可观测）。
"""

from dataclasses import dataclass, field

from app.guardrail import desensitize


@dataclass
class SecurityResult:
    clean_text: str
    sensitive_found: list[str] = field(default_factory=list)


def review_output(text: str) -> SecurityResult:
    found = desensitize.detect(text)
    clean = desensitize.desensitize_text(text)
    return SecurityResult(clean_text=clean, sensitive_found=found)
