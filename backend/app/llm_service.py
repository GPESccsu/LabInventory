"""LLM 服务层 — 业务代码唯一的 LLM 入口。

业务层只调用本模块，不直接 import provider 或 config。
Provider 切换完全通过环境变量完成，对业务层透明。
"""
from __future__ import annotations

import os
from typing import Any

from backend.app.llm import get_provider, parse_intent, reset_provider, summarize_result
from backend.app.llm.config import LLMConfig
from backend.app.llm.draft_builder import WRITE_INTENTS, build_draft
from backend.app.llm.intent import Intent, ParsedIntent
from backend.app.llm.query_executor import execute_query


class LLMService:
    """业务层 LLM 服务封装。"""

    def _get_service(self) -> Any:
        """延迟获取 InventoryService 实例（避免循环导入）。"""
        from backend.app.core import InventoryService

        db_path = os.getenv("LABINV_DB", "./lab_inventory.db")
        return InventoryService(db_path)

    def ping(self) -> dict[str, Any]:
        """检测当前 LLM provider 连通性。

        Returns:
            包含 ok, provider, model, detail 的字典。
        """
        config = LLMConfig.from_env()
        try:
            provider = get_provider(config)
            reply = provider.chat([{"role": "user", "content": "ping"}])
            return {
                "ok": True,
                "provider": config.provider,
                "model": config.model,
                "detail": reply[:200] if reply else "ok",
            }
        except Exception as exc:
            return {
                "ok": False,
                "provider": config.provider,
                "model": config.model,
                "detail": str(exc)[:200],
            }

    def chat(self, messages: list[dict[str, str]]) -> str:
        """多轮对话。"""
        provider = get_provider()
        return provider.chat(messages)

    def parse(self, text: str) -> ParsedIntent:
        """自然语言 → 结构化意图解析。"""
        provider = get_provider()
        return parse_intent(provider, text)

    def query(self, text: str) -> dict[str, Any]:
        """自然语言查询全流程：解析 → 执行 → 返回结果。

        LLM 不编造数据。流程：
        1. parse_intent: 自然语言 → 结构化意图 + 参数
        2. execute_query: 调用 InventoryService 获取真实数据
        3. 返回结构化结果（含中文 message）

        Args:
            text: 用户自然语言输入。

        Returns:
            {
                "intent": str,
                "params": dict,
                "ok": bool,
                "message": str,       # 中文回答
                "data": list | dict,   # 原始查询数据
                "confidence": str,
            }
        """
        # 1. 解析意图
        parsed = self.parse(text)

        # 2. 执行真实查询
        inv_service = self._get_service()
        result = execute_query(inv_service, parsed)

        return {
            "intent": parsed.intent,
            "params": parsed.params,
            "ok": result["ok"],
            "message": result["message"],
            "data": result["data"],
            "confidence": parsed.confidence,
        }

    def draft_stock_op(self, text: str) -> dict[str, Any]:
        """自然语言 → 库存操作草稿（不执行）。

        只生成草稿供用户确认，不写入数据库。

        Args:
            text: 用户自然语言输入。

        Returns:
            草稿字典，包含 op, fields, missing_fields, is_complete 等。
        """
        parsed = self.parse(text)

        # 如果不是写操作意图，返回提示
        if parsed.intent not in WRITE_INTENTS:
            return {
                "op": parsed.intent,
                "op_name": "",
                "api_path": "",
                "fields": parsed.params,
                "missing_fields": [],
                "field_defs": [],
                "is_complete": False,
                "description": (
                    f"无法识别为库存操作。识别到的意图：{parsed.intent}。\n"
                    "支持的操作：入库、出库、移库、调整。\n"
                    "示例：「把 50 个 STM32F103 入库到 G01-01」"
                ),
                "confidence": parsed.confidence,
                "raw_text": text,
            }

        provider = get_provider()
        return build_draft(parsed, provider=provider)

    def execute_draft(self, op: str, fields: dict[str, Any]) -> dict[str, Any]:
        """执行已确认的操作草稿。

        通过现有 InventoryService 执行，不绕过任何业务规则和 trigger。

        Args:
            op: 操作类型 (stock_in / stock_out / stock_move / stock_adjust)
            fields: 用户确认后的完整字段。

        Returns:
            {"ok": bool, "detail": str}
        """
        svc = self._get_service()
        try:
            if op == Intent.STOCK_IN:
                svc.stock_in(
                    mpn=fields["mpn"],
                    location=fields["location"],
                    qty=int(fields["qty"]),
                    condition=fields.get("condition", "new"),
                    note=fields.get("note", ""),
                )
                return {"ok": True, "detail": f"入库成功：{fields['mpn']} × {fields['qty']} → {fields['location']}"}

            elif op == Intent.STOCK_OUT:
                svc.stock_out(
                    mpn=fields["mpn"],
                    location=fields["location"],
                    qty=int(fields["qty"]),
                    project_code=fields.get("project_code", ""),
                    ref=fields.get("ref", ""),
                    note=fields.get("note", ""),
                    operator=fields.get("operator", ""),
                )
                return {"ok": True, "detail": f"出库成功：{fields['mpn']} × {fields['qty']} ← {fields['location']}"}

            elif op == Intent.STOCK_MOVE:
                svc.stock_move(
                    mpn=fields["mpn"],
                    from_location=fields["from_location"],
                    to_location=fields["to_location"],
                    qty=int(fields["qty"]),
                    note=fields.get("note", ""),
                    operator=fields.get("operator", ""),
                )
                return {"ok": True, "detail": f"移库成功：{fields['mpn']} × {fields['qty']}"}

            elif op == Intent.STOCK_ADJUST:
                svc.stock_adjust(
                    mpn=fields["mpn"],
                    location=fields["location"],
                    add_qty=int(fields.get("add_qty", 0)),
                    sub_qty=int(fields.get("sub_qty", 0)),
                    note=fields.get("note", ""),
                    ref=fields.get("ref", ""),
                    operator=fields.get("operator", ""),
                )
                return {"ok": True, "detail": f"调整成功：{fields['mpn']} @ {fields['location']}"}

            else:
                return {"ok": False, "detail": f"不支持的操作类型: {op}"}

        except Exception as exc:
            return {"ok": False, "detail": f"执行失败：{exc}"}

    def summarize(self, intent: str, data: Any, instruction: str = "") -> str:
        """结构化数据 → 中文摘要。"""
        provider = get_provider()
        return summarize_result(provider, intent, data, instruction)

    def get_config(self) -> dict[str, str | int]:
        """返回当前配置（隐藏 api_key）。"""
        return LLMConfig.from_env().safe_dict()

    @staticmethod
    def reset() -> None:
        """重置 provider 单例（用于测试或热切换）。"""
        reset_provider()


# 模块级单例，供 API 层直接使用
llm_service = LLMService()
