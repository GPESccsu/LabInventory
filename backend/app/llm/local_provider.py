"""Local LLM Provider — 通过 OpenAI 兼容 API 调用本地推理服务。

支持 Ollama、vLLM、LocalAI 等部署了 OpenAI 兼容接口的本地服务。
典型 base_url: http://localhost:11434（Ollama）或 http://localhost:8080（vLLM）。
"""
from __future__ import annotations

import json
import logging
from typing import Any

import requests

from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.config import LLMConfig

logger = logging.getLogger(__name__)


class LocalProvider(BaseLLMProvider):
    """通过 OpenAI 兼容 API 调用本地模型。"""

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        # Ollama 默认 /v1/chat/completions；vLLM 同理
        base = config.api_base.rstrip("/")
        self._chat_url = f"{base}/v1/chat/completions"

    def _call_chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """调用 OpenAI 兼容的 chat completions 接口。"""
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
        }
        payload.update(kwargs)

        try:
            resp = requests.post(
                self._chat_url,
                json=payload,
                timeout=self.config.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except requests.Timeout:
            logger.error("本地模型请求超时 (timeout=%ds)", self.config.timeout)
            raise RuntimeError(f"本地模型请求超时（{self.config.timeout}s）")
        except requests.ConnectionError:
            logger.error("无法连接本地模型服务: %s", self._chat_url)
            raise RuntimeError(f"无法连接本地模型服务: {self.config.api_base}")
        except (requests.HTTPError, KeyError, IndexError) as exc:
            logger.error("本地模型调用失败: %s", exc)
            raise RuntimeError(f"本地模型调用失败: {exc}")

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return self._call_chat(messages, **kwargs)

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
        return self._call_chat([{"role": "user", "content": prompt}], max_tokens=512)
