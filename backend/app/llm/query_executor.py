"""查询执行器 — 将解析后的意图映射到 InventoryService 真实查询。

LLM 不编造数据。本模块负责：
1. 接收 ParsedIntent（意图 + 结构化参数）
2. 调用 InventoryService 对应方法获取真实数据
3. 返回结构化结果供后续摘要生成
"""
from __future__ import annotations

from typing import Any

from backend.app.core import InventoryError, InventoryService
from backend.app.llm.intent import Intent, ParsedIntent


def execute_query(service: InventoryService, parsed: ParsedIntent) -> dict[str, Any]:
    """根据解析后的意图执行真实数据库查询。

    Args:
        service: InventoryService 实例。
        parsed: 解析后的意图。

    Returns:
        {
            "ok": bool,
            "intent": str,
            "data": list | dict | str,
            "message": str,       # 简要中文描述
        }
    """
    intent = parsed.intent
    params = parsed.params

    try:
        if intent == Intent.QUERY_STOCK:
            return _query_stock(service, params)
        elif intent == Intent.QUERY_PARTS:
            return _query_parts(service, params)
        elif intent == Intent.QUERY_LEDGER:
            return _query_ledger(service, params)
        elif intent == Intent.PROJECT_STATUS:
            return _project_status(service, params)
        elif intent == Intent.HELP:
            return _help()
        elif intent == Intent.UNKNOWN:
            return {
                "ok": False,
                "intent": intent,
                "data": [],
                "message": (
                    "无法识别您的问题。您可以尝试：\n"
                    "- 查询库存：「STM32F103 还有多少库存？」\n"
                    "- 查询项目状态：「项目 PROJ-001 缺哪些料？」\n"
                    "- 查询出入库记录：「这个月有哪些出库记录？」\n"
                    "- 查询元件信息：「有哪些电阻？」\n"
                    "- 输入「帮助」查看全部功能"
                ),
            }
        else:
            # 写操作意图（stock_in/out 等）不在此处执行
            return {
                "ok": False,
                "intent": intent,
                "data": [],
                "message": f"意图 [{intent}] 为写操作，不支持通过自然语言直接执行。请使用对应的表单操作。",
            }
    except InventoryError as exc:
        return {
            "ok": False,
            "intent": intent,
            "data": [],
            "message": f"查询失败：{exc}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "intent": intent,
            "data": [],
            "message": f"查询出错：{exc}",
        }


def _query_stock(service: InventoryService, params: dict[str, Any]) -> dict[str, Any]:
    """查询库存。"""
    query = params.get("mpn", "")
    location = params.get("location", "")
    rows = service.list_stock(query, location)

    if not rows:
        hint = ""
        if query:
            hint += f"MPN/名称含「{query}」"
        if location:
            hint += f" 库位含「{location}」"
        return {
            "ok": True,
            "intent": Intent.QUERY_STOCK,
            "data": [],
            "message": f"未找到匹配的库存记录。{('搜索条件：' + hint) if hint else ''}",
        }

    total_qty = sum(r.get("qty", 0) for r in rows)
    locations = sorted(set(r.get("location", "") for r in rows))
    return {
        "ok": True,
        "intent": Intent.QUERY_STOCK,
        "data": rows,
        "message": (
            f"找到 {len(rows)} 条库存记录，总数量 {total_qty}。"
            f"分布在 {len(locations)} 个库位：{', '.join(locations[:5])}"
            + ("..." if len(locations) > 5 else "") + "。"
        ),
    }


def _query_parts(service: InventoryService, params: dict[str, Any]) -> dict[str, Any]:
    """查询元件。"""
    query = params.get("mpn", "")
    rows = service.search_parts(query)

    if not rows:
        return {
            "ok": True,
            "intent": Intent.QUERY_PARTS,
            "data": [],
            "message": f"未找到匹配的元件。" + (f"搜索条件：「{query}」" if query else ""),
        }

    categories = sorted(set(r.get("category", "") for r in rows if r.get("category")))
    return {
        "ok": True,
        "intent": Intent.QUERY_PARTS,
        "data": rows,
        "message": (
            f"找到 {len(rows)} 个元件。"
            + (f"分类：{', '.join(categories[:5])}" if categories else "")
            + ("..." if len(categories) > 5 else "") + "。"
        ),
    }


def _query_ledger(service: InventoryService, params: dict[str, Any]) -> dict[str, Any]:
    """查询出入库记录。"""
    project_code = params.get("project_code", "")
    mpn = params.get("mpn", "")
    since = params.get("since", "")
    rows = service.query_ledger(project_code, mpn, since)

    if not rows:
        filters = []
        if project_code:
            filters.append(f"项目={project_code}")
        if mpn:
            filters.append(f"MPN={mpn}")
        if since:
            filters.append(f"自 {since} 起")
        return {
            "ok": True,
            "intent": Intent.QUERY_LEDGER,
            "data": [],
            "message": "未找到匹配的出入库记录。" + (f"筛选条件：{'，'.join(filters)}" if filters else ""),
        }

    # 按 doc_type 统计
    type_counts: dict[str, int] = {}
    for r in rows:
        dt = r.get("doc_type", "?")
        type_counts[dt] = type_counts.get(dt, 0) + 1
    summary_parts = [f"{t} {c} 条" for t, c in sorted(type_counts.items())]

    return {
        "ok": True,
        "intent": Intent.QUERY_LEDGER,
        "data": rows,
        "message": f"找到 {len(rows)} 条记录。类型分布：{', '.join(summary_parts)}。",
    }


def _project_status(service: InventoryService, params: dict[str, Any]) -> dict[str, Any]:
    """查询项目物料状态。"""
    project_code = params.get("project_code", "")
    if not project_code:
        # 没有指定项目，列出所有项目让用户选择
        projects = service.list_projects("")
        if not projects:
            return {
                "ok": True,
                "intent": Intent.PROJECT_STATUS,
                "data": [],
                "message": "系统中暂无项目。",
            }
        project_list = [f"- {p['code']}（{p['name']}）" for p in projects[:10]]
        return {
            "ok": False,
            "intent": Intent.PROJECT_STATUS,
            "data": projects,
            "message": (
                "请指定项目编码。当前系统中的项目：\n"
                + "\n".join(project_list)
                + ("\n..." if len(projects) > 10 else "")
            ),
        }

    try:
        status_rows = service.get_project_status(project_code)
    except InventoryError:
        return {
            "ok": False,
            "intent": Intent.PROJECT_STATUS,
            "data": [],
            "message": f"项目不存在：{project_code}",
        }

    if not status_rows:
        return {
            "ok": True,
            "intent": Intent.PROJECT_STATUS,
            "data": [],
            "message": f"项目 {project_code} 暂无 BOM 记录。",
        }

    # 分析缺料情况
    total_items = len(status_rows)
    shortage_items = [r for r in status_rows if r.get("shortage_if_reserve_now", 0) > 0]
    fully_reserved = [r for r in status_rows if r.get("remaining_to_reserve", 0) == 0]

    message_parts = [f"项目 {project_code} BOM 共 {total_items} 种物料。"]
    if shortage_items:
        message_parts.append(f"其中 {len(shortage_items)} 种物料有缺口：")
        for s in shortage_items[:5]:
            message_parts.append(
                f"  - {s.get('mpn', '?')}（{s.get('part_desc', '')}）"
                f"需求 {s.get('req_qty', 0)}，可用 {s.get('available_stock', 0)}，"
                f"缺口 {s.get('shortage_if_reserve_now', 0)}"
            )
        if len(shortage_items) > 5:
            message_parts.append(f"  ...共 {len(shortage_items)} 种缺料")
    else:
        message_parts.append("所有物料库存充足，无缺口。")

    message_parts.append(f"已完成预留的物料：{len(fully_reserved)}/{total_items}。")

    return {
        "ok": True,
        "intent": Intent.PROJECT_STATUS,
        "data": status_rows,
        "message": "\n".join(message_parts),
    }


def _help() -> dict[str, Any]:
    return {
        "ok": True,
        "intent": Intent.HELP,
        "data": [],
        "message": (
            "我可以帮您查询以下信息：\n"
            "1. **库存查询**：「STM32F103 还有多少库存？」「C409-G01 有哪些物料？」\n"
            "2. **元件查询**：「有哪些电阻？」「查一下 10k 电阻」\n"
            "3. **项目状态**：「项目 PROJ-001 缺哪些料？」「项目 XX 的物料状态」\n"
            "4. **出入库记录**：「这个月有哪些出库记录？」「STM32 的入库记录」\n\n"
            "请用自然语言描述您的问题，系统会查询真实数据后回答。"
        ),
    }
