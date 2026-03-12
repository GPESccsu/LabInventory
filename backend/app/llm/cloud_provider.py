"""Cloud LLM Provider — 调用云端 LLM API。

支持三种 API 类型：
- openai:     OpenAI / Azure OpenAI 兼容
- anthropic:  Anthropic Messages API
- deepseek:   DeepSeek（OpenAI 兼容）
"""
from __future__ import annotations

import json
import logging
from typing import Any

import requests

from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.config import LLMConfig

logger = logging.getLogger(__name__)

# 各 API 类型的默认 base URL
_DEFAULT_BASES: dict[str, str] = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "deepseek": "https://api.deepseek.com",
}


class CloudProvider(BaseLLMProvider):
    """通过云端 API 调用 LLM。"""

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        if not config.api_key:
            raise ValueError("云端 provider 需要设置 LABINV_LLM_API_KEY")
        self._api_type = config.api_type

    def _call_openai_compat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
    ) -> str:
        """调用 OpenAI 兼容接口（openai / deepseek）。"""
        base = self.config.api_base.rstrip("/")
        url = f"{base}/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": max_tokens or self.config.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.config.timeout)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except requests.Timeout:
            raise RuntimeError(f"云端 API 请求超时（{self.config.timeout}s）")
        except requests.ConnectionError:
            raise RuntimeError(f"无法连接云端 API: {base}")
        except (requests.HTTPError, KeyError, IndexError) as exc:
            logger.error("云端 API 调用失败: %s", exc)
            raise RuntimeError(f"云端 API 调用失败: {exc}")

    def _call_anthropic(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
    ) -> str:
        """调用 Anthropic Messages API。"""
        base = self.config.api_base.rstrip("/")
        url = f"{base}/v1/messages"

        # 分离 system 消息
        system_text = ""
        chat_messages: list[dict[str, str]] = []
        for m in messages:
            if m["role"] == "system":
                system_text += m["content"] + "\n"
            else:
                chat_messages.append({"role": m["role"], "content": m["content"]})

        # Anthropic 要求至少一条 user 消息
        if not chat_messages:
            chat_messages = [{"role": "user", "content": "你好"}]

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": chat_messages,
            "max_tokens": max_tokens or self.config.max_tokens,
        }
        if system_text.strip():
            payload["system"] = system_text.strip()

        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.config.timeout)
            resp.raise_for_status()
            data = resp.json()
            # Anthropic 返回 content 数组
            content_blocks = data.get("content", [])
            return "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        except requests.Timeout:
            raise RuntimeError(f"Anthropic API 请求超时（{self.config.timeout}s）")
        except requests.ConnectionError:
            raise RuntimeError(f"无法连接 Anthropic API: {base}")
        except (requests.HTTPError, KeyError) as exc:
            logger.error("Anthropic API 调用失败: %s", exc)
            raise RuntimeError(f"Anthropic API 调用失败: {exc}")

    def _call(self, messages: list[dict[str, str]], max_tokens: int | None = None) -> str:
        if self._api_type == "anthropic":
            return self._call_anthropic(messages, max_tokens)
        # openai / deepseek 都走 OpenAI 兼容接口
        return self._call_openai_compat(messages, max_tokens)

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return self._call(messages)

    def classify_intent(self, text: str, candidates: list[str]) -> str:
        system = (
            "你是一个库存管理意图分类器。"
            f"请将用户输入分类为以下意图之一：{', '.join(candidates)}"
        )
        try:
            result = self.chat_json(
                system_prompt=system,
                user_prompt=text,
                schema_hint={"intent": "str — 意图名称，必须是候选列表中的一个"},
            )
            intent = str(result.get("intent", "unknown")).strip()
            return intent if intent in candidates else "unknown"
        except (ValueError, RuntimeError):
            return "unknown"

    def extract_fields(self, text: str, field_schema: dict[str, str]) -> dict[str, Any]:
        system = (
            "从用户输入的自然语言中提取结构化字段。"
            "未提取到的字段不要包含在结果中。"
        )
        schema_hint = {k: f"{v} — 字段值" for k, v in field_schema.items()}
        try:
            return self.chat_json(
                system_prompt=system,
                user_prompt=text,
                schema_hint=schema_hint,
            )
        except (ValueError, RuntimeError):
            logger.warning("extract_fields chat_json 失败，输入: %s", text[:200])
            return {}

    def summarize(self, data: str, instruction: str = "") -> str:
        prompt = f"请用中文简要总结以下数据：\n{data}"
        if instruction:
            prompt += f"\n\n额外要求：{instruction}"
        return self._call([{"role": "user", "content": prompt}], max_tokens=512)
