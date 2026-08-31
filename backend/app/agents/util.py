# @repo: https://github.com/xiaotuolu/DevSupport-AI
"""Agent 通用工具：JSON 解析 + 结构化卡片渲染。"""

import json
import re

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_json(text: str) -> dict:
    """从 LLM 输出中稳健解析 JSON（容忍 ```json 围栏与多余文本）。"""
    if not text:
        return {}
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    m = _JSON_RE.search(text)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def normalize_card(raw: dict) -> dict:
    """规范化结构化卡片字段。"""
    def _list(v):
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []

    return {
        "conclusion": str(raw.get("conclusion", "")).strip(),
        "evidence": _list(raw.get("evidence")),
        "steps": _list(raw.get("steps")),
    }


def render_card(card: dict) -> str:
    """把结构化卡片渲染为 markdown（用于记忆/缓存/兜底显示）。"""
    parts = []
    if card.get("conclusion"):
        parts.append(f"**结论**：{card['conclusion']}")
    if card.get("evidence"):
        parts.append("**证据**：\n" + "\n".join(f"- {e}" for e in card["evidence"]))
    if card.get("steps"):
        parts.append("**建议步骤**：\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(card["steps"], 1)))
    return "\n\n".join(parts)
