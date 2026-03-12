"""LLM Provider 抽象基类。

所有 provider（mock / local / cloud）都必须实现此接口。
业务层只依赖此抽象，不直接 import 具体 provider，
从而保证更换模型供应商时业务代码零改动。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.app.llm.config import LLMConfig


class BaseLLMProvider(ABC):
    """LLM provider 统一接口。"""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """通用多轮对话。

        Args:
            messages: OpenAI 格式消息列表，如
                [{"role": "system", "content": "..."},
                 {"role": "user",   "content": "..."}]
        Returns:
            模型生成的文本。
        """
        ...

    @abstractmethod
    def extract_fields(self, text: str, field_schema: dict[str, str]) -> dict[str, Any]:
        """从自然语言中抽取结构化字段。

        Args:
            text: 用户输入的自然语言。
            field_schema: 期望字段及类型，如
                {"mpn": "str", "qty": "int", "location": "str"}
        Returns:
            抽取到的字段字典，如
                {"mpn": "STM32F103C8T6", "qty": 10, "location": "C409-G01-01-01"}
            未能抽取的字段不出现在返回值中。
        """
        ...

    @abstractmethod
    def classify_intent(self, text: str, candidates: list[str]) -> str:
        """将自然语言分类为预定义意图之一。

        Args:
            text: 用户输入。
            candidates: 候选意图列表，如
                ["stock_in", "stock_out", "query_stock", "project_status", ...]
        Returns:
            最匹配的意图字符串；若无法判断返回 "unknown"。
        """
        ...

    @abstractmethod
    def summarize(self, data: str, instruction: str = "") -> str:
        """将结构化数据生成中文自然语言摘要。

        Args:
            data: JSON 字符串或表格文本。
            instruction: 可选的额外指示（如 "请关注缺料情况"）。
        Returns:
            中文摘要文本。
        """
        ...
