"""LLM 服务层 — 业务代码唯一的 LLM 入口。

业务层只调用本模块，不直接 import provider 或 config。
Provider 切换完全通过环境变量完成，对业务层透明。
"""
from __future__ import annotations

from typing import Any

from backend.app.llm import get_provider, parse_intent, reset_provider, summarize_result
from backend.app.llm.config import LLMConfig
from backend.app.llm.intent import ParsedIntent


class LLMService:
    """业务层 LLM 服务封装。"""

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
