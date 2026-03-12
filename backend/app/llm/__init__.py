"""LLM 子包 — 提供 provider 工厂函数。

使用方式::

    from backend.app.llm import get_provider
    provider = get_provider()          # 根据环境变量自动选择
    provider.chat([{"role": "user", "content": "你好"}])
"""
from __future__ import annotations

from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.config import LLMConfig
from backend.app.llm.intent import Intent, ParsedIntent, parse_intent
from backend.app.llm.summarizer import summarize_result

__all__ = [
    "BaseLLMProvider",
    "LLMConfig",
    "Intent",
    "ParsedIntent",
    "get_provider",
    "parse_intent",
    "summarize_result",
]

# 单例缓存
_provider_instance: BaseLLMProvider | None = None


def get_provider(config: LLMConfig | None = None) -> BaseLLMProvider:
    """根据配置返回 LLM provider 实例（单例）。

    Args:
        config: 可选配置，默认从环境变量读取。

    Returns:
        BaseLLMProvider 实例。

    Raises:
        ValueError: 不支持的 provider 类型。
    """
    global _provider_instance

    if config is None:
        config = LLMConfig.from_env()

    # 如果已有实例且配置未变，直接返回
    if _provider_instance is not None and _provider_instance.config == config:
        return _provider_instance

    if config.provider == "mock":
        from backend.app.llm.mock_provider import MockProvider

        _provider_instance = MockProvider(config)
    elif config.provider == "local":
        from backend.app.llm.local_provider import LocalProvider

        _provider_instance = LocalProvider(config)
    elif config.provider == "cloud":
        from backend.app.llm.cloud_provider import CloudProvider

        _provider_instance = CloudProvider(config)
    else:
        raise ValueError(
            f"不支持的 LLM provider: {config.provider!r}。"
            f"支持的值: mock, local, cloud。"
            f"请设置环境变量 LABINV_LLM_PROVIDER"
        )

    return _provider_instance


def reset_provider() -> None:
    """重置 provider 单例（用于测试）。"""
    global _provider_instance
    _provider_instance = None
