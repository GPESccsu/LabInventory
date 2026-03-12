"""意图解析器 — 自然语言 → 结构化操作指令。

将用户的自然语言输入解析为：
1. intent（意图类别）
2. params（操作所需的结构化参数）

然后交给 InventoryService 现有方法执行。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.app.llm.base import BaseLLMProvider


class Intent(str, Enum):
    """支持的意图枚举。"""

    STOCK_IN = "stock_in"
    STOCK_OUT = "stock_out"
    STOCK_MOVE = "stock_move"
    STOCK_ADJUST = "stock_adjust"
    RESERVE = "reserve"
    RELEASE = "release"
    CONSUME = "consume"
    QUERY_STOCK = "query_stock"
    QUERY_PARTS = "query_parts"
    QUERY_LEDGER = "query_ledger"
    PROJECT_STATUS = "project_status"
    HELP = "help"
    UNKNOWN = "unknown"


# 每种意图需要的字段 schema
INTENT_FIELD_SCHEMAS: dict[str, dict[str, str]] = {
    Intent.STOCK_IN: {"mpn": "str", "location": "str", "qty": "int"},
    Intent.STOCK_OUT: {"mpn": "str", "location": "str", "qty": "int", "project_code": "str"},
    Intent.STOCK_MOVE: {"mpn": "str", "from_location": "str", "to_location": "str", "qty": "int"},
    Intent.STOCK_ADJUST: {"mpn": "str", "location": "str", "qty": "int"},
    Intent.RESERVE: {"project_code": "str", "mpn": "str", "location": "str", "qty": "int"},
    Intent.RELEASE: {"alloc_id": "int"},
    Intent.CONSUME: {"alloc_id": "int"},
    Intent.QUERY_STOCK: {"mpn": "str", "location": "str"},
    Intent.QUERY_PARTS: {"mpn": "str"},
    Intent.QUERY_LEDGER: {"project_code": "str", "mpn": "str", "since": "str"},
    Intent.PROJECT_STATUS: {"project_code": "str"},
    Intent.HELP: {},
    Intent.UNKNOWN: {},
}

# 每种意图的必填字段
INTENT_REQUIRED_FIELDS: dict[str, list[str]] = {
    Intent.STOCK_IN: ["mpn", "location", "qty"],
    Intent.STOCK_OUT: ["mpn", "location", "qty"],
    Intent.STOCK_MOVE: ["mpn", "from_location", "to_location", "qty"],
    Intent.STOCK_ADJUST: ["mpn", "location", "qty"],
    Intent.RESERVE: ["project_code", "mpn", "location", "qty"],
    Intent.RELEASE: ["alloc_id"],
    Intent.CONSUME: ["alloc_id"],
    Intent.QUERY_STOCK: [],     # 可选过滤
    Intent.QUERY_PARTS: [],     # 可选过滤
    Intent.QUERY_LEDGER: [],    # 可选过滤
    Intent.PROJECT_STATUS: ["project_code"],
    Intent.HELP: [],
    Intent.UNKNOWN: [],
}


@dataclass
class ParsedIntent:
    """解析结果。"""

    intent: str
    params: dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    confidence: str = "mock"  # "mock" | "low" | "medium" | "high"
    raw_text: str = ""

    @property
    def is_complete(self) -> bool:
        """所有必填字段都已填充。"""
        return len(self.missing_fields) == 0

    @property
    def is_query(self) -> bool:
        """是否为只读查询（不修改数据）。"""
        return self.intent in (
            Intent.QUERY_STOCK,
            Intent.QUERY_PARTS,
            Intent.QUERY_LEDGER,
            Intent.PROJECT_STATUS,
            Intent.HELP,
            Intent.UNKNOWN,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "params": self.params,
            "missing_fields": self.missing_fields,
            "is_complete": self.is_complete,
            "is_query": self.is_query,
            "confidence": self.confidence,
        }


def parse_intent(provider: BaseLLMProvider, text: str) -> ParsedIntent:
    """使用 LLM provider 解析用户输入为结构化意图。

    Args:
        provider: LLM provider 实例。
        text: 用户自然语言输入。

    Returns:
        ParsedIntent 包含意图、参数、缺失字段等信息。
    """
    all_intents = [e.value for e in Intent]

    # 1. 分类意图
    intent_str = provider.classify_intent(text, all_intents)
    try:
        intent = Intent(intent_str)
    except ValueError:
        intent = Intent.UNKNOWN

    # 2. 抽取字段
    schema = INTENT_FIELD_SCHEMAS.get(intent, {})
    params: dict[str, Any] = {}
    if schema:
        params = provider.extract_fields(text, schema)

    # 3. 检查必填字段
    required = INTENT_REQUIRED_FIELDS.get(intent, [])
    missing = [f for f in required if f not in params or params[f] is None]

    return ParsedIntent(
        intent=intent.value,
        params=params,
        missing_fields=missing,
        confidence="mock" if provider.config.provider == "mock" else "medium",
        raw_text=text,
    )
