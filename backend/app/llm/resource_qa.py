"""项目资源问答模块。

基于项目关联的 project_resources 构建上下文，
让 LLM 在资源信息范围内回答用户问题。

当前为最小可用版本（V1）：
- 直接将 name / type / uri / tags / note 拼为文本上下文
- 未来可扩展为文档切片 + 向量检索

数据流：
    用户问题 + project_code
           |
           v
    InventoryService.list_resources(code)   -- 拉取资源元数据
           |
           v
    build_resource_context(resources)       -- 组装上下文文本
           |
           v
    provider.qa_with_context(question, ctx) -- LLM 回答
           |
           v
    ResourceQAResponse (answer + sources)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# 单条资源上下文最大字符数（防止单条过长撑爆 prompt）
_MAX_ITEM_CHARS = 500
# 总上下文最大字符数
_MAX_CONTEXT_CHARS = 8000


@dataclass
class ResourceContext:
    """组装后的资源上下文，供 LLM 消费。"""

    text: str
    """拼接后的纯文本上下文。"""
    source_names: list[str] = field(default_factory=list)
    """参与上下文的资源名称列表（用于引用溯源）。"""
    total_resources: int = 0
    """项目资源总数。"""

    # --- 预留：未来文档切片扩展 ---
    # chunks: list[dict] = field(default_factory=list)
    # embeddings: list[list[float]] = field(default_factory=list)


def build_resource_context(
    resources: list[dict[str, Any]],
    *,
    query: str = "",
) -> ResourceContext:
    """将 project_resources 行列表组装为 LLM 可消费的上下文。

    当前策略（V1）：
    - 把每条资源的 type / name / uri / tags / note 拼成一段文本
    - 如果有 query，按关键词简单排序（命中多的排前面）
    - 截断到 _MAX_CONTEXT_CHARS

    未来升级路径：
    - V2: 对 uri 指向的文件做文本抽取 + 切片
    - V3: 接入向量库做语义检索
    """
    if not resources:
        return ResourceContext(text="", source_names=[], total_resources=0)

    # 构建每条资源的文本片段
    items: list[tuple[int, str, str]] = []  # (relevance_score, name, text)
    query_lower = query.lower()
    keywords = query_lower.split() if query_lower else []

    for r in resources:
        name = r.get("name", "")
        r_type = r.get("type", "")
        uri = r.get("uri", "")
        tags = r.get("tags", "") or ""
        note = r.get("note", "") or ""

        parts = []
        if r_type:
            parts.append(f"[{r_type}]")
        if name:
            parts.append(f"名称: {name}")
        if uri:
            parts.append(f"路径: {uri}")
        if tags:
            parts.append(f"标签: {tags}")
        if note:
            parts.append(f"说明: {note}")

        snippet = " | ".join(parts)
        if len(snippet) > _MAX_ITEM_CHARS:
            snippet = snippet[:_MAX_ITEM_CHARS] + "..."

        # 简单关键词命中计分
        score = 0
        if keywords:
            combined = f"{name} {tags} {note} {r_type} {uri}".lower()
            for kw in keywords:
                if kw in combined:
                    score += 1

        items.append((score, name, snippet))

    # 按相关度降序排列
    items.sort(key=lambda x: x[0], reverse=True)

    # 拼接并截断
    lines: list[str] = []
    source_names: list[str] = []
    total_len = 0
    for _, name, snippet in items:
        if total_len + len(snippet) + 1 > _MAX_CONTEXT_CHARS:
            break
        lines.append(f"- {snippet}")
        if name:
            source_names.append(name)
        total_len += len(snippet) + 1

    context_text = "\n".join(lines)

    return ResourceContext(
        text=context_text,
        source_names=source_names,
        total_resources=len(resources),
    )


_QA_SYSTEM_PROMPT = """\
你是实验室库存管理系统的项目资源问答助手。
用户会提供一个项目关联的资源列表作为上下文，请基于这些资源信息回答用户的问题。

规则：
1. 只基于提供的资源上下文回答，不要编造信息。
2. 如果上下文中没有足够依据，请明确说明"当前项目资源中未找到足够依据"。
3. 回答时尽量引用命中的资源名称，方便用户溯源。
4. 使用中文回答。
5. 保持简洁，不要重复列出所有资源（除非用户明确要求）。
"""


def ask_resource_qa(
    provider: BaseLLMProvider,
    question: str,
    context: ResourceContext,
) -> dict[str, Any]:
    """基于资源上下文回答用户问题。

    Args:
        provider: LLM provider 实例。
        question: 用户问题。
        context: 构建好的资源上下文。

    Returns:
        {
            "answer": str,          # LLM 回答
            "sources": list[str],   # 引用的资源名称
            "total_resources": int, # 项目资源总数
        }
    """
    if not context.text:
        return {
            "answer": "当前项目没有关联的资源记录，无法回答问题。请先为项目添加资源。",
            "sources": [],
            "total_resources": 0,
        }

    user_prompt = (
        f"以下是当前项目的资源列表（共 {context.total_resources} 条）：\n"
        f"{context.text}\n\n"
        f"用户问题：{question}"
    )

    messages = [
        {"role": "system", "content": _QA_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        answer = provider.chat(messages)
    except Exception as exc:
        logger.error("资源问答 LLM 调用失败: %s", exc)
        answer = f"问答服务暂时不可用：{exc}"

    return {
        "answer": answer,
        "sources": context.source_names,
        "total_resources": context.total_resources,
    }
