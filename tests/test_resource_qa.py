from __future__ import annotations

from backend.app.llm.config import LLMConfig
from backend.app.llm.mock_provider import MockProvider
from backend.app.llm.resource_qa import ResourceContext, ask_resource_qa


def test_ask_resource_qa_uses_mock_fallback_answer() -> None:
    provider = MockProvider(LLMConfig.from_env())
    context = ResourceContext(
        text="- [doc] 名称: 设计文档 | 说明: 包含系统设计",
        source_names=["设计文档", "测试计划"],
        total_resources=2,
    )

    result = ask_resource_qa(provider, "系统架构是什么？", context)

    assert "Mock LLM 模式" in result["answer"]
    assert "设计文档" in result["answer"]
    assert result["sources"] == ["设计文档", "测试计划"]
    assert result["total_resources"] == 2
    assert "[Mock] 识别意图" not in result["answer"]


def test_ask_resource_qa_calls_provider_chat_for_non_mock() -> None:
    class DummyProvider(MockProvider):
        def chat(self, messages, **kwargs):  # type: ignore[override]
            return "来自上下文的回答"

    cfg = LLMConfig(
        provider="local",
        model="dummy",
        api_base="http://localhost",
        api_key="",
        api_type="openai",
        timeout=30,
        max_tokens=256,
    )
    provider = DummyProvider(cfg)
    context = ResourceContext(text="- [doc] 名称: 规格书", source_names=["规格书"], total_resources=1)

    result = ask_resource_qa(provider, "有哪些规格？", context)

    assert result["answer"] == "来自上下文的回答"
    assert result["sources"] == ["规格书"]
    assert result["total_resources"] == 1
