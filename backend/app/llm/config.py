"""LLM 配置管理。

通过环境变量控制 provider 选择和模型参数。
零配置时默认使用 mock provider（不依赖任何外部服务）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    """LLM 提供者配置。"""

    provider: str       # "mock" | "local" | "cloud"
    model: str          # 模型名，如 "qwen2.5:7b" / "claude-sonnet-4-20250514"
    api_base: str       # 本地模型 API 地址 或 云端 base URL
    api_key: str        # 云端 API key（mock/local 时可为空）
    api_type: str       # 云端 API 类型: "openai" | "anthropic" | "deepseek"
    timeout: int        # 请求超时（秒）
    max_tokens: int     # 最大生成 token 数

    @classmethod
    def from_env(cls) -> LLMConfig:
        """从环境变量构造配置。"""
        return cls(
            provider=os.getenv("LABINV_LLM_PROVIDER", "mock"),
            model=os.getenv("LABINV_LLM_MODEL", ""),
            api_base=os.getenv("LABINV_LLM_API_BASE", "http://localhost:11434"),
            api_key=os.getenv("LABINV_LLM_API_KEY", ""),
            api_type=os.getenv("LABINV_LLM_API_TYPE", "openai"),
            timeout=int(os.getenv("LABINV_LLM_TIMEOUT", "30")),
            max_tokens=int(os.getenv("LABINV_LLM_MAX_TOKENS", "2048")),
        )

    def safe_dict(self) -> dict[str, str | int]:
        """返回不含敏感信息的配置字典（隐藏 api_key）。"""
        return {
            "provider": self.provider,
            "model": self.model,
            "api_base": self.api_base,
            "api_key": "***" if self.api_key else "",
            "api_type": self.api_type,
            "timeout": self.timeout,
            "max_tokens": self.max_tokens,
        }
