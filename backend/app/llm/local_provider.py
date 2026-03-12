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
        prompt = (
            f"你是一个库存管理意图分类器。请将用户输入分类为以下意图之一：\n"
            f"{', '.join(candidates)}\n\n"
            f"用户输入：{text}\n\n"
            f"请只返回意图名称，不要其他内容。"
        )
        result = self._call_chat([{"role": "user", "content": prompt}], max_tokens=32)
        result = result.strip().strip('"').strip("'")
        return result if result in candidates else "unknown"

    def extract_fields(self, text: str, field_schema: dict[str, str]) -> dict[str, Any]:
        schema_desc = json.dumps(field_schema, ensure_ascii=False)
        prompt = (
            f"从以下文本中提取结构化字段。\n"
            f"字段定义：{schema_desc}\n\n"
            f"用户输入：{text}\n\n"
            f"请以 JSON 格式返回提取到的字段，未提取到的字段不要包含。"
            f"只返回 JSON，不要其他内容。"
        )
        result = self._call_chat([{"role": "user", "content": prompt}], max_tokens=256)
        try:
            # 尝试从回复中提取 JSON
            result = result.strip()
            if result.startswith("```"):
                result = result.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(result)
        except (json.JSONDecodeError, IndexError):
            logger.warning("字段抽取返回非 JSON: %s", result[:200])
            return {}

    def summarize(self, data: str, instruction: str = "") -> str:
        prompt = f"请用中文简要总结以下数据：\n{data}"
        if instruction:
            prompt += f"\n\n额外要求：{instruction}"
        return self._call_chat([{"role": "user", "content": prompt}], max_tokens=512)
