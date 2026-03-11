from __future__ import annotations

import os
from typing import Any

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("LABINV_API_BASE", "http://127.0.0.1:8000")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def api_get(path: str, **kwargs) -> requests.Response:
    return requests.get(f"{API_BASE}{path}", timeout=30, **kwargs)


def api_post(path: str, **kwargs) -> requests.Response:
    return requests.post(f"{API_BASE}{path}", timeout=30, **kwargs)


def api_delete(path: str, **kwargs) -> requests.Response:
    return requests.delete(f"{API_BASE}{path}", timeout=30, **kwargs)


def _items(resp: requests.Response) -> list[dict[str, Any]]:
    """Extract 'items' list from API response, handling errors."""
    if not resp.ok:
        return []
    data = resp.json()
    if isinstance(data, dict):
        return data.get("items", [])
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# Tab: 系统概览
# ---------------------------------------------------------------------------

def tab_overview() -> None:
    st.subheader("系统概览")
    try:
        resp = api_get("/api/health")
        if resp.ok:
            h = resp.json()
            c1, c2, c3 = st.columns(3)
            c1.metric("物料种类", h.get("parts_count", 0))
            c2.metric("库存记录", h.get("stock_rows", 0))
            c3.metric("项目数量", h.get("projects_count", 0))
            st.caption(f"数据库路径：{h.get('db_path', '—')}")
        else:
            st.error(f"API 连接失败：{resp.status_code}")
    except Exception as exc:
        st.error(f"无法连接 API（{API_BASE}）：{exc}")


# ---------------------------------------------------------------------------
# Tab: 物料管理
# ---------------------------------------------------------------------------

def tab_parts() -> None:
    st.subheader("物料管理")

    # --- 搜索物料 ---
    st.markdown("#### 搜索物料")
    query = st.text_input("搜索关键词（MPN / 名称 / 分类 / 封装）", "", key="parts_query")
    parts = _items(api_get("/api/parts", params={"query": query}))
    if parts:
        st.dataframe(pd.DataFrame(parts), use_container_width=True, hide_index=True)
    else:
        st.info("没有匹配的物料")

    st.divider()

    # --- 从立创商城导入 ---
    st.markdown("#### 从立创商城导入物料")
    st.caption("输入立创商城商品链接，自动抓取物料信息并导入数据库，同时下载数据手册。")
    with st.form("lcsc_import_form"):
        lcsc_url = st.text_input("立创商品链接", "", placeholder="https://item.szlcsc.com/...")
        submitted = st.form_submit_button("导入物料", type="primary")
    if submitted:
        if not lcsc_url.strip():
            st.warning("请输入立创商品链接")
        else:
            with st.spinner("正在从立创商城抓取数据，请稍候..."):
                try:
                    r = api_post("/api/lcsc/import", json={"url": lcsc_url.strip()})
                    if r.ok:
                        data = r.json()
                        st.success(f"导入成功！MPN: {data['mpn']}，物料ID: {data['part_id']}")
                        st.json(data)
                    else:
                        detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
                        st.error(f"导入失败：{detail}")
                except Exception as exc:
                    st.error(f"请求失败：{exc}")


# ---------------------------------------------------------------------------
# Tab: 库存管理
# ---------------------------------------------------------------------------

def tab_stock() -> None:
    st.subheader("库存管理")

    # --- 库存查询 ---
    st.markdown("#### 库存查询")
    c1, c2 = st.columns(2)
    sq = c1.text_input("搜索（MPN / 名称）", "", key="stock_query")
    sl = c2.text_input("按库位过滤", "", key="stock_loc")
    stock_items = _items(api_get("/api/stock", params={"query": sq, "location": sl}))
    if stock_items:
        df = pd.DataFrame(stock_items)
        st.dataframe(df, use_container_width=True, hide_index=True)
        total = sum(s.get("qty", 0) for s in stock_items)
        st.caption(f"共 {len(stock_items)} 条记录，总数量 {total}")
    else:
        st.info("没有匹配的库存记录")

    st.divider()

    # --- 库存操作 ---
    st.markdown("#### 库存操作")
    op = st.selectbox("操作类型", ["入库", "出库", "移库", "调整"], key="stock_op")

    if op == "入库":
        with st.form("stock_in_form"):
            c1, c2, c3 = st.columns(3)
            mpn = c1.text_input("MPN", key="si_mpn")
            loc = c2.text_input("库位", key="si_loc")
            qty = c3.number_input("数量", min_value=1, value=1, key="si_qty")
            c4, c5 = st.columns(2)
            condition = c4.selectbox("状态", ["new", "used", "refurbished"], key="si_cond")
            note = c5.text_input("备注", "", key="si_note")
            if st.form_submit_button("执行入库", type="primary"):
                r = api_post("/api/stock/in", json={"mpn": mpn, "location": loc, "qty": int(qty), "condition": condition, "note": note})
                if r.ok:
                    st.success(f"入库成功：{mpn} @ {loc} +{qty}")
                else:
                    st.error(_err(r))

    elif op == "出库":
        with st.form("stock_out_form"):
            c1, c2, c3 = st.columns(3)
            mpn = c1.text_input("MPN", key="so_mpn")
            loc = c2.text_input("库位", key="so_loc")
            qty = c3.number_input("数量", min_value=1, value=1, key="so_qty")
            c4, c5 = st.columns(2)
            proj = c4.text_input("项目编码（可选）", "", key="so_proj")
            ref = c5.text_input("参考单号（可选）", "", key="so_ref")
            c6, c7 = st.columns(2)
            note = c6.text_input("备注", "", key="so_note")
            operator = c7.text_input("操作人", "", key="so_op")
            if st.form_submit_button("执行出库", type="primary"):
                r = api_post("/api/stock/out", json={
                    "mpn": mpn, "location": loc, "qty": int(qty),
                    "project_code": proj, "ref": ref, "note": note, "operator": operator,
                })
                if r.ok:
                    st.success(f"出库成功：{mpn} @ {loc} -{qty}")
                else:
                    st.error(_err(r))

    elif op == "移库":
        with st.form("stock_move_form"):
            c1, c2 = st.columns(2)
            mpn = c1.text_input("MPN", key="sm_mpn")
            qty = c2.number_input("数量", min_value=1, value=1, key="sm_qty")
            c3, c4 = st.columns(2)
            from_loc = c3.text_input("源库位", key="sm_from")
            to_loc = c4.text_input("目标库位", key="sm_to")
            c5, c6 = st.columns(2)
            note = c5.text_input("备注", "", key="sm_note")
            operator = c6.text_input("操作人", "", key="sm_op")
            if st.form_submit_button("执行移库", type="primary"):
                r = api_post("/api/stock/move", json={
                    "mpn": mpn, "from_location": from_loc, "to_location": to_loc,
                    "qty": int(qty), "note": note, "operator": operator,
                })
                if r.ok:
                    st.success(f"移库成功：{mpn} {from_loc} → {to_loc} qty={qty}")
                else:
                    st.error(_err(r))

    elif op == "调整":
        with st.form("stock_adjust_form"):
            c1, c2 = st.columns(2)
            mpn = c1.text_input("MPN", key="sa_mpn")
            loc = c2.text_input("库位", key="sa_loc")
            c3, c4, c5 = st.columns(3)
            direction = c3.selectbox("方向", ["增加", "减少"], key="sa_dir")
            adj_qty = c4.number_input("数量", min_value=1, value=1, key="sa_qty")
            note = c5.text_input("原因（必填）", "", key="sa_note")
            c6, c7 = st.columns(2)
            ref = c6.text_input("参考单号", "", key="sa_ref")
            operator = c7.text_input("操作人", "", key="sa_op")
            if st.form_submit_button("执行调整", type="primary"):
                if not note.strip():
                    st.warning("调整原因不能为空")
                else:
                    payload = {
                        "mpn": mpn, "location": loc, "note": note,
                        "ref": ref, "operator": operator,
                        "add_qty": int(adj_qty) if direction == "增加" else 0,
                        "sub_qty": int(adj_qty) if direction == "减少" else 0,
                    }
                    r = api_post("/api/stock/adjust", json=payload)
                    if r.ok:
                        st.success(f"调整成功：{mpn} @ {loc} {direction} {adj_qty}")
                    else:
                        st.error(_err(r))

    st.divider()

    # --- 库位列表 ---
    st.markdown("#### 库位列表")
    if st.button("加载库位列表", key="load_loc"):
        locs = _items(api_get("/api/locations"))
        if locs:
            st.dataframe(pd.DataFrame(locs), use_container_width=True, hide_index=True)
        else:
            st.info("没有库位记录")


def _err(resp: requests.Response) -> str:
    """Extract error detail from response."""
    try:
        data = resp.json()
        return data.get("detail", resp.text)
    except Exception:
        return resp.text


# ---------------------------------------------------------------------------
# Tab: 项目管理
# ---------------------------------------------------------------------------

def tab_projects() -> None:
    st.subheader("项目管理")

    # --- 项目列表 ---
    st.markdown("#### 项目列表")
    pq = st.text_input("搜索项目（code / 名称 / 负责人）", "", key="proj_query")
    projects = _items(api_get("/api/projects", params={"query": pq}))
    if projects:
        st.dataframe(pd.DataFrame(projects), use_container_width=True, hide_index=True)
    else:
        st.info("没有匹配的项目")

    st.divider()

    # --- 创建/更新项目 ---
    st.markdown("#### 创建 / 更新项目")
    with st.form("create_project"):
        c1, c2 = st.columns(2)
        code = c1.text_input("项目编码", "", key="pj_code")
        name = c2.text_input("项目名称", "", key="pj_name")
        c3, c4 = st.columns(2)
        owner = c3.text_input("负责人", "", key="pj_owner")
        note = c4.text_input("备注", "", key="pj_note")
        if st.form_submit_button("创建 / 更新项目", type="primary"):
            r = api_post("/api/projects", json={"code": code, "name": name, "owner": owner, "note": note})
            if r.ok:
                st.success("项目已保存")
            else:
                st.error(_err(r))

    st.divider()

    # --- 项目详情 ---
    codes = [p["code"] for p in projects]
    if not codes:
        return
    st.markdown("#### 项目详情")
    selected = st.selectbox("选择项目", options=codes, key="proj_select")
    if not selected:
        return

    # 项目状态
    st.markdown("##### BOM + 库存 + 预留状态")
    status_rows = _items(api_get(f"/api/projects/{selected}/status"))
    if status_rows:
        st.dataframe(pd.DataFrame(status_rows), use_container_width=True, hide_index=True)
    else:
        st.info("没有 BOM 记录")

    # 预留明细
    st.markdown("##### 预留明细")
    alloc_rows = _items(api_get(f"/api/projects/{selected}/allocs"))
    if alloc_rows:
        st.dataframe(pd.DataFrame(alloc_rows), use_container_width=True, hide_index=True)
    else:
        st.info("没有预留记录")

    # 设置 BOM
    st.markdown("##### 设置 BOM 需求")
    with st.form("bom_set_form"):
        c1, c2, c3 = st.columns(3)
        bom_mpn = c1.text_input("MPN", key="bom_mpn")
        bom_req = c2.number_input("需求数量", min_value=1, value=1, key="bom_req")
        bom_pri = c3.number_input("优先级", min_value=1, max_value=5, value=2, key="bom_pri")
        bom_note = st.text_input("备注", "", key="bom_note")
        if st.form_submit_button("设置 BOM"):
            r = api_post(f"/api/projects/{selected}/bom", json={
                "items": [{"mpn": bom_mpn, "req_qty": int(bom_req), "priority": int(bom_pri), "note": bom_note}]
            })
            if r.ok:
                st.success("BOM 已更新")
            else:
                st.error(_err(r))

    # 预留
    st.markdown("##### 预留物料")
    with st.form("reserve_form"):
        c1, c2, c3 = st.columns(3)
        res_mpn = c1.text_input("MPN", key="res_mpn")
        res_loc = c2.text_input("库位", key="res_loc")
        res_qty = c3.number_input("预留数量", min_value=1, value=1, key="res_qty")
        res_note = st.text_input("备注", "", key="res_note")
        if st.form_submit_button("执行预留"):
            r = api_post(f"/api/projects/{selected}/reserve", json={
                "mpn": res_mpn, "location": res_loc, "qty": int(res_qty), "note": res_note,
            })
            if r.ok:
                st.success(f"预留成功：alloc_id={r.json()['alloc_id']}")
            else:
                st.error(_err(r))

    # 释放/消耗
    st.markdown("##### 释放 / 消耗预留")
    c1, c2 = st.columns(2)
    alloc_id = c1.number_input("alloc_id", min_value=1, value=1, key="alloc_id")
    action_note = c2.text_input("动作备注", "", key="alloc_note")
    c3, c4 = st.columns(2)
    if c3.button("释放", key="release_btn"):
        r = api_post(f"/api/allocs/{int(alloc_id)}/release", json={"note": action_note})
        st.success("释放成功") if r.ok else st.error(_err(r))
    if c4.button("消耗", key="consume_btn"):
        r = api_post(f"/api/allocs/{int(alloc_id)}/consume", json={"note": action_note})
        st.success("消耗成功") if r.ok else st.error(_err(r))


# ---------------------------------------------------------------------------
# Tab: 项目资源
# ---------------------------------------------------------------------------

def tab_resources() -> None:
    st.subheader("项目资源")
    code = st.text_input("项目编码", "", key="res_code")
    if not code:
        st.info("请输入项目编码以管理资源")
        return

    # --- 添加资源 ---
    st.markdown("#### 添加 / 更新资源")
    with st.form("resource_add_form"):
        c1, c2 = st.columns(2)
        r_type = c1.text_input("类型（type）", "doc", key="radd_type")
        name = c2.text_input("名称（name）", "", key="radd_name")
        uri = st.text_input("路径 / URL（uri）", "", key="radd_uri")
        c3, c4, c5 = st.columns(3)
        is_dir = c3.selectbox("是否目录", [1, 0], key="radd_isdir")
        tags = c4.text_input("标签（tags）", "", key="radd_tags")
        r_note = c5.text_input("备注（note）", "", key="radd_note")
        no_check = st.checkbox("跳过路径检查", key="radd_nocheck")
        if st.form_submit_button("新增 / 更新资源", type="primary"):
            r = api_post(f"/api/projects/{code}/resources", json={
                "type": r_type, "name": name, "uri": uri,
                "is_dir": is_dir, "tags": tags, "note": r_note, "no_check": no_check,
            })
            if r.ok:
                st.success("资源已保存")
            else:
                st.error(_err(r))

    st.divider()

    # --- 资源列表 ---
    st.markdown("#### 资源列表")
    rr = api_get(f"/api/projects/{code}/resources")
    res_items = _items(rr)
    if res_items:
        st.dataframe(pd.DataFrame(res_items), use_container_width=True, hide_index=True)
    elif rr.ok:
        st.info("暂无资源")
    else:
        st.error(_err(rr))

    st.divider()

    # --- 删除资源 ---
    st.markdown("#### 删除资源")
    with st.form("resource_del_form"):
        c1, c2 = st.columns(2)
        del_type = c1.text_input("type", key="rdel_type")
        del_uri = c2.text_input("uri", key="rdel_uri")
        if st.form_submit_button("删除资源"):
            r = api_delete(f"/api/projects/{code}/resources", json={"type": del_type, "uri": del_uri})
            if r.ok:
                st.success("删除完成")
            else:
                st.error(_err(r))

    # --- 检查有效性 ---
    if st.button("检查资源有效性", key="res_check"):
        r = api_post(f"/api/projects/{code}/resources/check")
        if r.ok:
            checks = _items(r)
            if checks:
                st.dataframe(pd.DataFrame(checks), use_container_width=True, hide_index=True)
            else:
                st.info("没有资源需要检查")
        else:
            st.error(_err(r))


# ---------------------------------------------------------------------------
# Tab: 交易流水
# ---------------------------------------------------------------------------

def tab_ledger() -> None:
    st.subheader("交易流水")
    c1, c2, c3 = st.columns(3)
    led_proj = c1.text_input("按项目过滤", "", key="led_proj")
    led_mpn = c2.text_input("按 MPN 过滤", "", key="led_mpn")
    led_since = c3.text_input("起始日期 (YYYY-MM-DD)", "", key="led_since")

    ledger = _items(api_get("/api/ledger", params={"project": led_proj, "mpn": led_mpn, "since": led_since}))
    if ledger:
        st.dataframe(pd.DataFrame(ledger), use_container_width=True, hide_index=True)
        st.caption(f"共 {len(ledger)} 条记录")
    else:
        st.info("没有匹配的流水记录")


# ---------------------------------------------------------------------------
# Tab: 导入导出
# ---------------------------------------------------------------------------

def tab_import_export() -> None:
    st.subheader("XLSX 批量导入")

    # --- 交易导入 ---
    st.markdown("#### 导入交易 XLSX")
    st.caption("上传 XLSX 文件，等价于 CLI 的 txn-import-xlsx 命令。支持 auto / transactions / stock-io 模式。")
    txn_file = st.file_uploader("选择交易 XLSX 文件", type=["xlsx"], key="txn_upload")
    c1, c2 = st.columns(2)
    txn_mode = c1.selectbox("导入模式", ["auto", "transactions", "stock-io"], key="txn_mode")
    txn_partial = c2.checkbox("允许部分成功", key="txn_partial")
    if st.button("导入交易 XLSX", type="primary", key="txn_import_btn") and txn_file is not None:
        files = {"file": (txn_file.name, txn_file.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = api_post("/api/txns/import-xlsx", files=files, data={"partial": str(txn_partial).lower(), "mode": txn_mode})
        if r.ok:
            data = r.json()
            st.success(f"导入完成：成功 {data.get('ok', 0)} 行，失败 {data.get('err', 0)} 行")
        else:
            st.error(_err(r))

    st.divider()

    # --- 资源导入 ---
    st.markdown("#### 导入项目资源 XLSX")
    st.caption("上传 XLSX 文件，批量导入项目资源。")
    res_file = st.file_uploader("选择资源 XLSX 文件", type=["xlsx"], key="res_upload")
    c1, c2 = st.columns(2)
    res_sheet = c1.text_input("Sheet 名称", "Resources", key="res_sheet")
    res_header = c2.number_input("表头行号", min_value=1, value=1, key="res_header")
    c3, c4 = st.columns(2)
    res_nocheck = c3.checkbox("跳过路径检查", key="res_nocheck")
    res_autocreate = c4.checkbox("自动创建项目", key="res_autocreate")
    if st.button("导入资源 XLSX", type="primary", key="res_import_btn") and res_file is not None:
        files = {"file": (res_file.name, res_file.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = api_post(
            "/api/projects/resources/import-xlsx",
            files=files,
            data={
                "sheet": res_sheet,
                "header_row": int(res_header),
                "no_check": str(res_nocheck).lower(),
                "auto_create_project": str(res_autocreate).lower(),
            },
        )
        if r.ok:
            data = r.json()
            st.success(f"导入完成：成功 {data.get('ok', 0)} 行，失败 {data.get('err', 0)} 行")
        else:
            st.error(_err(r))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="实验室库存系统", layout="wide")
    st.title("实验室库存与项目管理")
    st.caption(f"API 地址：{API_BASE}")

    tabs = st.tabs(["系统概览", "物料管理", "库存管理", "项目管理", "项目资源", "交易流水", "导入导出"])

    with tabs[0]:
        tab_overview()
    with tabs[1]:
        tab_parts()
    with tabs[2]:
        tab_stock()
    with tabs[3]:
        tab_projects()
    with tabs[4]:
        tab_resources()
    with tabs[5]:
        tab_ledger()
    with tabs[6]:
        tab_import_export()


if __name__ == "__main__":
    main()
