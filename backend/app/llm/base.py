"""LLM Provider 抽象基类。

所有 provider（mock / local / cloud）都必须实现此接口。
业务层只依赖此抽象，不直接 import 具体 provider，
从而保证更换模型供应商时业务代码零改动。
"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from backend.app.llm.config import LLMConfig

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any]:
    """从 LLM 回复文本中提取 JSON 对象。

    支持以下格式：
    - 纯 JSON: {"key": "value"}
    - Markdown code block: ```json\n{...}\n```
    - 带前后缀文字: 一些文字 {...} 一些文字

    Raises:
        ValueError: 无法从文本中提取有效 JSON。
    """
    text = text.strip()

    # 1. 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 尝试从 markdown code block 提取
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. 尝试找到第一个 { 到最后一个 } 之间的内容
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从回复中提取 JSON: {text[:200]}")


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

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """统一的结构化 JSON 输出接口。

        将 system_prompt + user_prompt 发送给模型，期望返回 JSON 对象。
        自动处理 JSON 提取和解析，子类可覆盖以利用原生 JSON mode。

        Args:
            system_prompt: 系统提示词（角色设定 + 输出格式要求）。
            user_prompt: 用户输入。
            schema_hint: 可选的期望输出 JSON schema 描述。
                帮助模型理解期望的输出结构，如：
                {"intent": "str — 意图名称", "confidence": "float — 置信度"}

        Returns:
            解析后的 dict。

        Raises:
            ValueError: 模型返回的内容无法解析为 JSON。
            RuntimeError: 模型调用失败。
        """
        # 构造 system 提示：追加 JSON 格式要求
        full_system = system_prompt.rstrip()
        if schema_hint:
            schema_desc = json.dumps(schema_hint, ensure_ascii=False, indent=2)
            full_system += f"\n\n期望输出 JSON 格式：\n{schema_desc}"
        full_system += "\n\n请只返回 JSON 对象，不要包含其他内容。"

        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": user_prompt},
        ]
        raw = self.chat(messages)
        try:
            return _extract_json(raw)
        except ValueError:
            logger.warning("chat_json 解析失败，原始回复: %s", raw[:300])
            raise

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
