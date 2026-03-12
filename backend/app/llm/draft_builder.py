"""草稿构建器 — 将解析后的写操作意图转为可确认的操作草稿。

草稿字段严格对齐现有 CLI / API 参数，确认执行时直接调用 InventoryService。
"""
from __future__ import annotations

from typing import Any

from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.intent import Intent, ParsedIntent

# 操作类型 → 中文名称
_OP_NAMES: dict[str, str] = {
    Intent.STOCK_IN: "入库",
    Intent.STOCK_OUT: "出库",
    Intent.STOCK_MOVE: "移库",
    Intent.STOCK_ADJUST: "调整",
}

# 操作类型 → 对应 API 路径
_OP_API_PATHS: dict[str, str] = {
    Intent.STOCK_IN: "/api/stock/in",
    Intent.STOCK_OUT: "/api/stock/out",
    Intent.STOCK_MOVE: "/api/stock/move",
    Intent.STOCK_ADJUST: "/api/stock/adjust",
}

# 操作类型 → 完整字段定义 {字段名: (中文标签, 类型, 是否必填, 默认值)}
_OP_FIELD_DEFS: dict[str, list[tuple[str, str, str, bool, Any]]] = {
    Intent.STOCK_IN: [
        ("mpn",       "MPN / 料号",  "str",  True,  ""),
        ("location",  "库位",        "str",  True,  ""),
        ("qty",       "数量",        "int",  True,  0),
        ("condition", "状态",        "str",  False, "new"),
        ("note",      "备注",        "str",  False, ""),
    ],
    Intent.STOCK_OUT: [
        ("mpn",          "MPN / 料号",  "str",  True,  ""),
        ("location",     "库位",        "str",  True,  ""),
        ("qty",          "数量",        "int",  True,  0),
        ("project_code", "项目编码",    "str",  False, ""),
        ("ref",          "参考号",      "str",  False, ""),
        ("note",         "备注",        "str",  False, ""),
        ("operator",     "操作员",      "str",  False, ""),
    ],
    Intent.STOCK_MOVE: [
        ("mpn",           "MPN / 料号",  "str",  True,  ""),
        ("from_location", "源库位",      "str",  True,  ""),
        ("to_location",   "目标库位",    "str",  True,  ""),
        ("qty",           "数量",        "int",  True,  0),
        ("note",          "备注",        "str",  False, ""),
        ("operator",      "操作员",      "str",  False, ""),
    ],
    Intent.STOCK_ADJUST: [
        ("mpn",      "MPN / 料号",   "str",  True,  ""),
        ("location", "库位",         "str",  True,  ""),
        ("add_qty",  "增加数量",     "int",  False, 0),
        ("sub_qty",  "减少数量",     "int",  False, 0),
        ("note",     "原因备注",     "str",  True,  ""),
        ("ref",      "参考号",       "str",  False, ""),
        ("operator", "操作员",       "str",  False, ""),
    ],
}

# 支持的写操作意图集合
WRITE_INTENTS = frozenset(_OP_NAMES.keys())


def build_draft(parsed: ParsedIntent, provider: BaseLLMProvider | None = None) -> dict[str, Any]:
    """根据 ParsedIntent 构建操作草稿。

    Returns:
        {
            "op": str,                # stock_in / stock_out / stock_move / stock_adjust
            "op_name": str,           # 中文名称
            "api_path": str,          # 对应 API 路径
            "fields": dict,           # 已填充的字段
            "missing_fields": [...],  # 缺失的必填字段 [{name, label, type}]
            "field_defs": [...],      # 完整字段定义（含中文标签）
            "is_complete": bool,      # 所有必填字段是否完整
            "description": str,       # 操作的中文描述
            "confidence": str,
            "raw_text": str,
        }
    """
    intent = parsed.intent
    if intent not in WRITE_INTENTS:
        return {
            "op": intent,
            "op_name": "",
            "api_path": "",
            "fields": parsed.params,
            "missing_fields": [],
            "field_defs": [],
            "is_complete": False,
            "description": f"意图 [{intent}] 不是库存操作，无法生成草稿。",
            "confidence": parsed.confidence,
            "raw_text": parsed.raw_text,
        }

    field_defs = _OP_FIELD_DEFS[intent]
    params = dict(parsed.params)

    # 用完整字段 schema 补充抽取（parse_intent 用的是精简 schema）
    if provider and parsed.raw_text:
        full_schema = {name: ftype for name, _label, ftype, _req, _default in field_defs}
        extra = provider.extract_fields(parsed.raw_text, full_schema)
        for k, v in extra.items():
            if k not in params or params[k] is None or params[k] == "":
                params[k] = v

    # 构建填充后的字段
    fields: dict[str, Any] = {}
    for name, _label, ftype, _required, default in field_defs:
        if name in params and params[name] is not None:
            val = params[name]
            # 类型转换
            if ftype == "int":
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    val = default
            fields[name] = val
        else:
            fields[name] = default

    # stock_adjust 特殊处理：从 qty 推断 add_qty / sub_qty
    if intent == Intent.STOCK_ADJUST and "qty" in params:
        qty = int(params["qty"])
        raw = parsed.raw_text.lower()
        if any(kw in raw for kw in ("减", "扣", "少", "sub")):
            fields["sub_qty"] = qty
            fields["add_qty"] = 0
        else:
            fields["add_qty"] = qty
            fields["sub_qty"] = 0

    # 检查缺失的必填字段
    missing = []
    for name, label, ftype, required, default in field_defs:
        if not required:
            continue
        val = fields.get(name)
        if val is None or val == "" or val == 0:
            # stock_adjust 特殊: add_qty / sub_qty 至少一个 > 0
            if intent == Intent.STOCK_ADJUST and name in ("add_qty", "sub_qty"):
                if fields.get("add_qty", 0) > 0 or fields.get("sub_qty", 0) > 0:
                    continue
            missing.append({"name": name, "label": label, "type": ftype})

    # 生成描述
    description = _build_description(intent, fields, missing)

    return {
        "op": intent,
        "op_name": _OP_NAMES[intent],
        "api_path": _OP_API_PATHS[intent],
        "fields": fields,
        "missing_fields": missing,
        "field_defs": [
            {"name": n, "label": l, "type": t, "required": r}
            for n, l, t, r, _ in field_defs
        ],
        "is_complete": len(missing) == 0,
        "description": description,
        "confidence": parsed.confidence,
        "raw_text": parsed.raw_text,
    }


def _build_description(intent: str, fields: dict[str, Any], missing: list[dict]) -> str:
    """生成操作的中文描述。"""
    op_name = _OP_NAMES.get(intent, "?")

    if missing:
        missing_labels = "、".join(m["label"] for m in missing)
        return f"[{op_name}] 草稿不完整，还需要填写：{missing_labels}"

    mpn = fields.get("mpn", "?")
    qty = fields.get("qty", 0)

    if intent == Intent.STOCK_IN:
        loc = fields.get("location", "?")
        return f"[入库] {mpn} × {qty} → {loc}"

    if intent == Intent.STOCK_OUT:
        loc = fields.get("location", "?")
        proj = fields.get("project_code", "")
        desc = f"[出库] {mpn} × {qty} ← {loc}"
        if proj:
            desc += f"（项目: {proj}）"
        return desc

    if intent == Intent.STOCK_MOVE:
        from_loc = fields.get("from_location", "?")
        to_loc = fields.get("to_location", "?")
        return f"[移库] {mpn} × {qty}：{from_loc} → {to_loc}"

    if intent == Intent.STOCK_ADJUST:
        loc = fields.get("location", "?")
        add_q = fields.get("add_qty", 0)
        sub_q = fields.get("sub_qty", 0)
        if add_q > 0:
            return f"[调整] {mpn} @ {loc} 增加 {add_q}"
        elif sub_q > 0:
            return f"[调整] {mpn} @ {loc} 减少 {sub_q}"
        return f"[调整] {mpn} @ {loc}"

    return f"[{op_name}] 操作草稿"
