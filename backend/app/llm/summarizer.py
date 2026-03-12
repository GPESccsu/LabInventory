"""摘要生成器 — 将结构化查询结果转为中文自然语言描述。"""
from __future__ import annotations

from typing import Any

from backend.app.llm.base import BaseLLMProvider


def summarize_result(
    provider: BaseLLMProvider,
    intent: str,
    data: Any,
    instruction: str = "",
) -> str:
    """将查询结果数据生成中文摘要。

    Args:
        provider: LLM provider 实例。
        intent: 意图类型（用于选择摘要策略）。
        data: 查询结果（dict / list / str）。
        instruction: 可选额外指示。

    Returns:
        中文摘要文本。
    """
    import json

    if data is None:
        return "未查询到相关数据。"

    if isinstance(data, str):
        text = data
    else:
        try:
            text = json.dumps(data, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(data)

    return provider.summarize(text, instruction=instruction)
