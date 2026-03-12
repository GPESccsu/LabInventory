"""项目资源问答 — 基于 project_resources 上下文的 LLM 问答。

数据流：
1. 用户选择项目 code + 输入问题
2. 从 project_resources 表检索该项目的全部资源
3. 将资源信息（name, type, uri, tags, note）拼接为上下文
4. 通过 LLM provider 生成回答，引用命中的资源名称
5. 如果依据不足，明确告知用户

当前为最小可用版本（V1），直接将资源元数据作为上下文。
后续可升级为：
- V2: 读取 URI 指向的文件内容，做文本切片
- V3: 引入向量检索（embedding + FAISS / ChromaDB）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.llm.base import BaseLLMProvider


@dataclass
class ResourceContext:
    """检索到的资源上下文片段。

    预留 chunk_text 字段，V1 阶段仅用元数据；
    V2+ 可填入文件内容切片。
    """

    resource_id: int
    resource_name: str
    resource_type: str
    uri: str
    tags: str
    note: str
    chunk_text: str = ""  # V2: 文档切片内容


@dataclass
class QAResult:
    """问答结果。"""

    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    has_sufficient_context: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": self.sources,
            "has_sufficient_context": self.has_sufficient_context,
        }


def build_resource_context(resources: list[dict[str, Any]]) -> list[ResourceContext]:
    """将 project_resources 行转为上下文片段列表。

    Args:
        resources: InventoryService.list_resources() 返回的 dict 列表。

    Returns:
        ResourceContext 列表，按 type 分组排序。
    """
    contexts: list[ResourceContext] = []
    for r in resources:
        contexts.append(ResourceContext(
            resource_id=r.get("id", 0),
            resource_name=r.get("name", ""),
            resource_type=r.get("type", ""),
            uri=r.get("uri", ""),
            tags=r.get("tags", "") or "",
            note=r.get("note", "") or "",
        ))
    return contexts


def format_context_text(contexts: list[ResourceContext]) -> str:
    """将上下文片段格式化为纯文本，供 LLM 阅读。

    格式示例：
    [资源 1] 类型：schematic | 名称：主板原理图 | URI：/docs/main_sch.pdf
             标签：PCB, 主板 | 备注：v2.1 版本
    """
    if not contexts:
        return "（该项目暂无关联资源）"

    lines: list[str] = []
    for i, ctx in enumerate(contexts, 1):
        parts = [
            f"[资源 {i}] 类型：{ctx.resource_type}",
            f"名称：{ctx.resource_name}",
            f"URI：{ctx.uri}",
        ]
        if ctx.tags:
            parts.append(f"标签：{ctx.tags}")
        if ctx.note:
            parts.append(f"备注：{ctx.note}")
        lines.append(" | ".join(parts))

        # V2: 如果有文档切片内容，附加在下方
        if ctx.chunk_text:
            lines.append(f"  内容摘要：{ctx.chunk_text[:500]}")

    return "\n".join(lines)


_SYSTEM_PROMPT = """\
你是实验室库存管理系统的项目资源问答助手。
用户会针对某个项目的关联资源提问，你需要基于提供的资源上下文回答问题。

规则：
1. 只基于提供的资源上下文回答，不要编造信息
2. 回答时尽量引用命中的资源名称（如「根据资源『主板原理图』...」）
3. 如果提供的资源信息不足以回答问题，请明确说「当前项目资源中未找到足够依据」
4. 使用中文回答
5. 回答要简洁明了
"""


def ask_resource_qa(
    provider: BaseLLMProvider,
    project_code: str,
    question: str,
    resources: list[dict[str, Any]],
) -> QAResult:
    """基于项目资源上下文回答用户问题。

    Args:
        provider: LLM provider 实例。
        project_code: 项目编码。
        question: 用户问题。
        resources: 该项目的资源列表（来自 InventoryService.list_resources()）。

    Returns:
        QAResult 包含回答文本和引用的资源来源。
    """
    contexts = build_resource_context(resources)
    context_text = format_context_text(contexts)

    user_prompt = (
        f"项目编码：{project_code}\n\n"
        f"项目关联资源：\n{context_text}\n\n"
        f"问题：{question}"
    )

    # 调用 LLM
    try:
        answer = provider.chat([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])
    except Exception as exc:
        return QAResult(
            answer=f"问答服务调用失败：{exc}",
            sources=[],
            has_sufficient_context=False,
        )

    # 检查回答是否表明依据不足
    insufficient_markers = ["未找到足够依据", "没有找到相关", "无法回答", "信息不足"]
    has_sufficient = not any(m in answer for m in insufficient_markers)

    # 收集被引用的资源（通过名称匹配）
    sources: list[dict[str, Any]] = []
    for ctx in contexts:
        if ctx.resource_name and ctx.resource_name in answer:
            sources.append({
                "id": ctx.resource_id,
                "name": ctx.resource_name,
                "type": ctx.resource_type,
                "uri": ctx.uri,
            })

    # 如果没有资源，标记依据不足
    if not resources:
        has_sufficient = False
        if "暂无关联资源" not in answer:
            answer = f"当前项目（{project_code}）暂无关联资源，无法回答您的问题。\n请先通过「项目资源」标签页添加相关资源。"

    return QAResult(
        answer=answer,
        sources=sources,
        has_sufficient_context=has_sufficient,
    )
