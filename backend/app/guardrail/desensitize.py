# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""敏感信息识别与脱敏。

用于三层脱敏：用户输入、工具结果/日志、最终输出。
识别：API Key / Secret / Token / 手机号 / 邮箱 / 身份证 / 完整签名 / 银行卡。
"""

import re

# (类型, 正则)。顺序敏感：先长串/特定格式，避免被短模式截断。
# 数字类用 (?<!\d)/(?!\d) 断言替代 \b，避免紧邻中文时词边界失效。
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("api_key", re.compile(r"(?<![A-Za-z0-9])((?:ak|sk)[-_][A-Za-z0-9_\-]{6,})")),
    ("secret", re.compile(r"(?i)(secret[_-]?key\s*[=:]\s*)([A-Za-z0-9]{6,})")),
    ("token", re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]{8,})")),
    ("idcard", re.compile(r"(?<!\d)(\d{6})(\d{8})(\d{3}[\dXx])(?!\d)")),
    ("bankcard", re.compile(r"(?<!\d)(\d{4})(\d{8,11})(\d{4})(?!\d)")),
    ("phone", re.compile(r"(?<!\d)(1[3-9]\d)(\d{4})(\d{4})(?!\d)")),
    ("email", re.compile(r"(?<![A-Za-z0-9._%+\-])([A-Za-z0-9._%+\-]{1,2})([A-Za-z0-9._%+\-]*)(@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")),
    ("signature", re.compile(r"(?<![a-fA-F0-9])([a-fA-F0-9]{8})([a-fA-F0-9]{24,})(?![a-fA-F0-9])")),
]


def _mask_api_key(m: re.Match) -> str:
    token = m.group(1)
    return f"{token[:7]}****{token[-4:]}"


def _mask_secret(m: re.Match) -> str:
    return f"{m.group(1)}****"


def _mask_token(m: re.Match) -> str:
    return f"{m.group(1)}****"


def _mask_idcard(m: re.Match) -> str:
    return f"{m.group(1)}********{m.group(3)[-1]}"


def _mask_bankcard(m: re.Match) -> str:
    return f"{m.group(1)}****{m.group(3)}"


def _mask_phone(m: re.Match) -> str:
    return f"{m.group(1)}****{m.group(3)}"


def _mask_email(m: re.Match) -> str:
    return f"{m.group(1)}***{m.group(3)}"


def _mask_signature(m: re.Match) -> str:
    return f"{m.group(1)}…(已脱敏)"


_MASKERS = {
    "api_key": _mask_api_key,
    "secret": _mask_secret,
    "token": _mask_token,
    "idcard": _mask_idcard,
    "bankcard": _mask_bankcard,
    "phone": _mask_phone,
    "email": _mask_email,
    "signature": _mask_signature,
}


def detect(text: str) -> list[str]:
    """返回文本中检测到的敏感信息类型列表。"""
    found = []
    for kind, pat in _PATTERNS:
        if pat.search(text):
            found.append(kind)
    return found


def desensitize_text(text: str) -> str:
    """对文本做脱敏替换。"""
    if not text:
        return text
    for kind, pat in _PATTERNS:
        text = pat.sub(_MASKERS[kind], text)
    return text


def desensitize_obj(obj):
    """递归脱敏 dict/list/str。"""
    if isinstance(obj, str):
        return desensitize_text(obj)
    if isinstance(obj, dict):
        return {k: desensitize_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [desensitize_obj(v) for v in obj]
    return obj
