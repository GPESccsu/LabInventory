"""Mock LLM Provider — 纯规则匹配，不依赖任何外部服务。

用于开发调试和单元测试。通过关键词 + 正则实现意图分类和字段抽取。
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.config import LLMConfig

# 意图关键词映射（优先级从上到下）
# 注意：顺序决定优先级。更具体的意图应排在前面。
_INTENT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("stock_in",        ["入库", "进货", "到货", "收货", "stock in", "stock-in"]),
    ("stock_move",      ["移库", "转移", "移动", "搬", "move"]),
    ("stock_adjust",    ["调整", "盘点", "adjust"]),
    ("reserve",         ["预留", "预定", "reserve"]),
    ("release",         ["释放", "release"]),
    ("consume",         ["消耗", "consume"]),
    ("project_status",  ["项目状态", "物料状态", "bom", "缺料", "缺哪些", "缺什么",
                         "项目概况", "项目详情", "project status"]),
    ("query_ledger",    ["流水", "台账", "记录", "历史", "ledger", "日志",
                         "出库记录", "入库记录", "这个月", "本月", "最近", "上个月"]),
    ("stock_out",       ["出库", "领料", "领取", "发料", "stock out", "stock-out"]),
    ("query_stock",     ["库存", "还有多少", "剩余", "stock", "余量", "数量",
                         "在哪", "哪些位置", "有货"]),
    ("query_parts",     ["元器件", "零件", "part", "物料信息", "参数", "电阻",
                         "电容", "芯片", "二极管", "三极管", "有哪些"]),
    ("help",            ["帮助", "你能做什么", "help", "功能"]),
]

# 字段抽取正则
_MPN_PATTERN = re.compile(
    r"(?:mpn|型号|料号)[：:\s]*([A-Za-z0-9\-_/.]+)"
    r"|([A-Z][A-Za-z0-9]{2,}[\-][A-Za-z0-9\-/.]+)"   # 带连字符 MPN
    r"|([A-Z]{2,}[0-9][A-Za-z0-9]{3,})"               # 连续 MPN 如 STM32F103C8T6
)
_QTY_PATTERN = re.compile(
    r"(?:数量|qty|quantity|个数)[：:\s]*(\d+)"
    r"|(\d+)\s*[个只片颗pcs]"
)
_LOC_PATTERN = re.compile(
    r"(?:位置|库位|location|loc)[：:\s]*([A-Za-z0-9\-_]+)"
    r"|(C409[\-][A-Za-z0-9\-]+)"
    r"|([GG][0-9]{2}[\-][0-9]{2}[\-][0-9]{2})"
)
_PROJECT_PATTERN = re.compile(
    r"(?:项目|project|proj)[：:\s]*([A-Za-z0-9\-_]+)"
)


def _extract_since(text: str) -> str:
    """从自然语言中提取日期范围的起始日期（YYYY-MM-DD 格式）。"""
    today = date.today()

    # 精确日期：2024-01-15 或 2024/01/15
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # "这个月" / "本月"
    if re.search(r"这个月|本月|当月", text):
        return today.replace(day=1).isoformat()

    # "上个月" / "上月"
    if re.search(r"上个月|上月", text):
        first_this_month = today.replace(day=1)
        last_month = first_this_month - timedelta(days=1)
        return last_month.replace(day=1).isoformat()

    # "最近N天" / "近N天"
    m = re.search(r"(?:最近|近)\s*(\d+)\s*天", text)
    if m:
        days = int(m.group(1))
        return (today - timedelta(days=days)).isoformat()

    # "今天"
    if "今天" in text:
        return today.isoformat()

    # "昨天"
    if "昨天" in text:
        return (today - timedelta(days=1)).isoformat()

    # "这周" / "本周"
    if re.search(r"这周|本周|这个星期", text):
        return (today - timedelta(days=today.weekday())).isoformat()

    return ""


class MockProvider(BaseLLMProvider):
    """基于关键词和正则的 Mock LLM Provider。"""

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break
        if not user_msg:
            return "请输入您的问题。"

        intent = self.classify_intent(user_msg, [c[0] for c in _INTENT_KEYWORDS])
        if intent == "help":
            return (
                "我可以帮您进行以下操作：\n"
                "- 查询库存（如：STM32F103 还有多少库存？）\n"
                "- 入库/出库/移库\n"
                "- 项目状态查询\n"
                "- 预留/释放/消耗\n"
                "- 流水记录查询\n"
                "请用自然语言描述您的需求。"
            )
        if intent == "unknown":
            return "抱歉，我无法理解您的意图。请尝试更明确地描述您的需求，或输入「帮助」查看支持的操作。"
        return f"[Mock] 识别意图: {intent}，请通过结构化接口调用。"

    def extract_fields(self, text: str, field_schema: dict[str, str]) -> dict[str, Any]:
        result: dict[str, Any] = {}

        if "mpn" in field_schema:
            m = _MPN_PATTERN.search(text)
            if m:
                result["mpn"] = m.group(1) or m.group(2) or m.group(3)

        if "qty" in field_schema:
            m = _QTY_PATTERN.search(text)
            if m:
                val = m.group(1) or m.group(2)
                result["qty"] = int(val)

        if "location" in field_schema:
            m = _LOC_PATTERN.search(text)
            if m:
                result["location"] = m.group(1) or m.group(2) or m.group(3)

        if "from_location" in field_schema:
            # 尝试匹配 "从 X 到 Y" 模式
            m = re.search(r"从\s*([A-Za-z0-9\-_]+)\s*(?:到|移到|转到)\s*([A-Za-z0-9\-_]+)", text)
            if m:
                result["from_location"] = m.group(1)
                if "to_location" in field_schema:
                    result["to_location"] = m.group(2)

        if "to_location" in field_schema and "to_location" not in result:
            m = re.search(r"(?:到|目标|to)[：:\s]*([A-Za-z0-9\-_]+)", text)
            if m:
                result["to_location"] = m.group(1)

        if "project_code" in field_schema:
            m = _PROJECT_PATTERN.search(text)
            if m:
                result["project_code"] = m.group(1)

        if "since" in field_schema:
            since = _extract_since(text)
            if since:
                result["since"] = since

        return result

    def classify_intent(self, text: str, candidates: list[str]) -> str:
        text_lower = text.lower()
        for intent, keywords in _INTENT_KEYWORDS:
            if intent not in candidates:
                continue
            for kw in keywords:
                if kw in text_lower:
                    return intent
        return "unknown"

    def summarize(self, data: str, instruction: str = "") -> str:
        try:
            parsed = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return f"[Mock 摘要] 数据: {data[:200]}"

        if isinstance(parsed, list):
            return f"[Mock 摘要] 共 {len(parsed)} 条记录。"
        if isinstance(parsed, dict):
            keys = list(parsed.keys())[:5]
            return f"[Mock 摘要] 数据包含字段: {', '.join(keys)}"
        return f"[Mock 摘要] {str(parsed)[:200]}"
