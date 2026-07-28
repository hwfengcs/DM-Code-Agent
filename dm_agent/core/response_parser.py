"""智能体响应的容错解析。

模型经常把 JSON 包在解释文字或 ```` ```json ```` 围栏里，也会带上中文引号或
尾随逗号。这里按「原文 → 围栏内容 → 首尾花括号之间 → 各自的修复版」的顺序
逐个试，第一个能解析成 JSON 对象的胜出，并如实报告是否用上了修复。
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from typing import Any

# 模型对终止动作的常见漂移写法，统一归一到 finish / task_complete。
TERMINAL_ACTION_ALIASES: dict[str, str] = {
    "finish": "finish",
    "final": "finish",
    "final_answer": "finish",
    "answer": "finish",
    "done": "finish",
    "completed": "finish",
    "complete": "finish",
    "stop": "finish",
    "task_done": "task_complete",
    "task_complete": "task_complete",
}


@dataclass(frozen=True)
class ParsedResponse:
    """一次成功解析的结果。

    ``repaired`` 为真表示原文不是一个严格的 JSON 对象，靠围栏提取、截取花括号
    或文本修复才解析出来——调用方据此累加 ``parse_repair_count``。
    """

    data: dict[str, Any]
    repaired: bool


def parse_agent_response(raw: str) -> ParsedResponse:
    """解析智能体响应。

    Args:
        raw: 智能体的原始响应字符串

    Returns:
        解析出的 JSON 对象及其是否经过修复

    Raises:
        ValueError: 响应为空，或没有任何候选片段能解析成 JSON 对象
    """
    candidate = raw.strip()
    if not candidate:
        raise ValueError("模型返回空响应。")

    for index, snippet in enumerate(json_candidates(candidate)):
        strict_json = is_strict_json_object(snippet)
        parsed = load_json_object(snippet)
        if parsed is not None:
            return ParsedResponse(
                data=parsed,
                repaired=index > 0 or snippet != candidate or not strict_json,
            )

    raise ValueError("Response is not a valid JSON object.")


def normalize_action(action: str) -> str:
    """把模型对终止动作的常见漂移写法归一化。"""
    normalized = re.sub(r"[^a-z0-9]+", "_", str(action).strip().lower()).strip("_")
    return TERMINAL_ACTION_ALIASES.get(normalized, action)


def json_candidates(candidate: str) -> list[str]:
    """按优先级列出所有值得一试的 JSON 片段。"""
    candidates = [candidate]

    fence_match = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.DOTALL | re.IGNORECASE)
    if fence_match:
        candidates.append(fence_match.group(1).strip())

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(candidate[start : end + 1])

    repaired_candidates = []
    for item in candidates:
        repaired = repair_json_text(item)
        if repaired != item:
            repaired_candidates.append(repaired)

    return candidates + repaired_candidates


def repair_json_text(text: str) -> str:
    """修掉中文引号与尾随逗号这两类最常见的手写 JSON 问题。"""
    text = text.strip()
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def load_json_object(text: str) -> dict[str, Any] | None:
    """尽力把文本读成 dict，失败返回 None（含读成非 dict 的情况）。"""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def is_strict_json_object(text: str) -> bool:
    """文本本身是否已经是合法的 JSON 对象（无需任何修复）。"""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, dict)
