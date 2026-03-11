from __future__ import annotations

import os

import requests
import streamlit as st

API_BASE = os.getenv("LABINV_API_BASE", "http://127.0.0.1:8000")


def api_get(path: str, **kwargs):
    return requests.get(f"{API_BASE}{path}", timeout=30, **kwargs)


def api_post(path: str, **kwargs):
    return requests.post(f"{API_BASE}{path}", timeout=30, **kwargs)


def api_delete(path: str, **kwargs):
    return requests.delete(f"{API_BASE}{path}", timeout=30, **kwargs)


# ---------------------------------------------------------------------------
# Sidebar: system health
# ---------------------------------------------------------------------------
def render_sidebar() -> None:
    st.sidebar.title("系统信息")
    try:
        h = api_get("/api/health").json()
        st.sidebar.metric("元件数", h.get("parts_count", "?"))
        st.sidebar.metric("库存行", h.get("stock_rows", "?"))
        st.sidebar.metric("项目数", h.get("projects_count", "?"))
        st.sidebar.caption(f"DB: {h.get('db_path', '?')}")
    except Exception:
        st.sidebar.warning("无法连接 API")
    st.sidebar.caption(f"API: {API_BASE}")


# ---------------------------------------------------------------------------
# Tab: Parts & Stock
# ---------------------------------------------------------------------------
def render_parts_stock_tab() -> None:
    st.subheader("元件查询")
    q = st.text_input("搜索元件（MPN/名称/分类/封装）", "", key="parts_q")
    try:
        parts = api_get("/api/parts", params={"query": q}).json().get("items", [])
    except Exception as exc:
        st.error(f"读取元件失败：{exc}")
        parts = []
    if parts:
        st.dataframe(parts, use_container_width=True)
    else:
        st.info("没有找到元件。")

    st.divider()
    st.subheader("库存查询")
    c1, c2 = st.columns(2)
    sq = c1.text_input("搜索库存（MPN/名称）", "", key="stock_q")
    sl = c2.text_input("筛选库位", "", key="stock_loc")
    try:
        stock = api_get("/api/stock", params={"query": sq, "location": sl}).json().get("items", [])
    except Exception as exc:
        st.error(f"读取库存失败：{exc}")
        stock = []
    if stock:
        st.dataframe(stock, use_container_width=True)
    else:
        st.info("没有库存记录。")


# ---------------------------------------------------------------------------
# Tab: Stock Operations
# ---------------------------------------------------------------------------
def render_stock_ops_tab() -> None:
    op = st.selectbox("操作类型", ["入库 (IN)", "出库 (OUT)", "移库 (MOVE)", "调整 (ADJUST)"], key="stock_op")

    if op.startswith("入库"):
        st.subheader("入库")
        with st.form("stock_in_form"):
            c1, c2 = st.columns(2)
            mpn = c1.text_input("MPN")
            location = c2.text_input("库位")
            qty = c1.number_input("数量", min_value=1, value=1)
            condition = c2.selectbox("状态", ["new", "used", "refurbished"])
            note = st.text_input("备注", "")
            if st.form_submit_button("执行入库"):
                r = api_post("/api/stock/in", json={"mpn": mpn, "location": location, "qty": int(qty), "condition": condition, "note": note})
                if r.ok:
                    st.success(r.json().get("detail", "入库成功"))
                else:
                    st.error(r.text)

    elif op.startswith("出库"):
        st.subheader("出库")
        with st.form("stock_out_form"):
            c1, c2 = st.columns(2)
            mpn = c1.text_input("MPN")
            location = c2.text_input("库位")
            qty = c1.number_input("数量", min_value=1, value=1)
            project_code = c2.text_input("项目编码（可选）", "")
            ref = c1.text_input("参考号", "")
            note = c2.text_input("备注", "")
            operator = st.text_input("操作员", "")
            if st.form_submit_button("执行出库"):
                r = api_post("/api/stock/out", json={
                    "mpn": mpn, "location": location, "qty": int(qty),
                    "project_code": project_code, "ref": ref, "note": note, "operator": operator,
                })
                if r.ok:
                    st.success(r.json().get("detail", "出库成功"))
                else:
                    st.error(r.text)

    elif op.startswith("移库"):
        st.subheader("移库")
        with st.form("stock_move_form"):
            c1, c2 = st.columns(2)
            mpn = c1.text_input("MPN")
            from_loc = c2.text_input("源库位")
            to_loc = c1.text_input("目标库位")
            qty = c2.number_input("数量", min_value=1, value=1)
            note = c1.text_input("备注", "")
            operator = c2.text_input("操作员", "")
            if st.form_submit_button("执行移库"):
                r = api_post("/api/stock/move", json={
                    "mpn": mpn, "from_location": from_loc, "to_location": to_loc,
                    "qty": int(qty), "note": note, "operator": operator,
                })
                if r.ok:
                    st.success(r.json().get("detail", "移库成功"))
                else:
                    st.error(r.text)

    elif op.startswith("调整"):
        st.subheader("调整")
        with st.form("stock_adjust_form"):
            c1, c2 = st.columns(2)
            mpn = c1.text_input("MPN")
            location = c2.text_input("库位")
            adjust_type = c1.selectbox("调整方向", ["增加", "减少"])
            qty = c2.number_input("调整数量", min_value=1, value=1)
            note = c1.text_input("原因备注（必填）", "")
            ref = c2.text_input("参考号", "")
            operator = st.text_input("操作员", "")
            if st.form_submit_button("执行调整"):
                payload = {
                    "mpn": mpn, "location": location, "note": note, "ref": ref, "operator": operator,
                    "add_qty": int(qty) if adjust_type == "增加" else 0,
                    "sub_qty": int(qty) if adjust_type == "减少" else 0,
                }
                r = api_post("/api/stock/adjust", json=payload)
                if r.ok:
                    st.success(r.json().get("detail", "调整成功"))
                else:
                    st.error(r.text)


# ---------------------------------------------------------------------------
# Tab: Project Management
# ---------------------------------------------------------------------------
def render_project_tab() -> None:
    st.subheader("项目列表与创建")
    q = st.text_input("搜索项目（code/name/owner）", "", key="proj_q")
    try:
        projects = api_get("/api/projects", params={"query": q}).json().get("items", [])
    except Exception as exc:
        st.error(f"读取项目失败：{exc}")
        projects = []
    if projects:
        st.dataframe(projects, use_container_width=True)

    with st.form("create_project"):
        st.markdown("#### 创建/更新项目")
        c1, c2 = st.columns(2)
        code = c1.text_input("项目编码", "")
        name = c2.text_input("项目名称", "")
        owner = c1.text_input("负责人", "")
        note = c2.text_input("备注", "")
        if st.form_submit_button("创建/更新项目"):
            r = api_post("/api/projects", json={"code": code, "name": name, "owner": owner, "note": note})
            if r.ok:
                st.success("项目已保存")
            else:
                st.error(r.text)

    st.divider()
    codes = [p["code"] for p in projects]
    selected = st.selectbox("选择项目查看详情", options=[""] + codes, key="proj_sel")
    if selected:
        # --- Project Status ---
        st.markdown("### 项目状态（BOM + 库存 + 预留）")
        try:
            status_rows = api_get(f"/api/projects/{selected}/status").json().get("items", [])
            st.dataframe(status_rows, use_container_width=True)
        except Exception as exc:
            st.error(f"获取项目状态失败：{exc}")

        # --- BOM Management ---
        st.markdown("### BOM 管理")
        with st.form("bom_form"):
            st.caption("批量设置 BOM（每行一个物料，提交后覆盖现有需求量）")
            bom_mpn = st.text_input("MPN", key="bom_mpn")
            c1, c2 = st.columns(2)
            bom_qty = c1.number_input("需求数量", min_value=1, value=1, key="bom_qty")
            bom_priority = c2.number_input("优先级", min_value=1, max_value=5, value=2, key="bom_pri")
            bom_note = st.text_input("备注", "", key="bom_note")
            if st.form_submit_button("设置 BOM"):
                r = api_post(f"/api/projects/{selected}/bom", json={
                    "items": [{"mpn": bom_mpn, "req_qty": int(bom_qty), "priority": int(bom_priority), "note": bom_note}]
                })
                if r.ok:
                    st.success(r.json().get("detail", "BOM 已更新"))
                else:
                    st.error(r.text)

        # --- Allocation Details ---
        st.markdown("### 预留明细")
        try:
            alloc_rows = api_get(f"/api/projects/{selected}/allocs").json().get("items", [])
            st.dataframe(alloc_rows, use_container_width=True)
        except Exception as exc:
            st.error(f"获取预留明细失败：{exc}")

        # --- Reserve ---
        with st.form("reserve_form"):
            st.markdown("#### 执行预留")
            c1, c2 = st.columns(2)
            mpn = c1.text_input("MPN", key="rsv_mpn")
            location = c2.text_input("库位", key="rsv_loc")
            qty = c1.number_input("预留数量", min_value=1, value=1, key="rsv_qty")
            note = c2.text_input("备注", "", key="rsv_note")
            if st.form_submit_button("执行预留"):
                r = api_post(f"/api/projects/{selected}/reserve", json={"mpn": mpn, "location": location, "qty": int(qty), "note": note})
                if r.ok:
                    st.success(f"预留成功：alloc_id={r.json()['alloc_id']}")
                else:
                    st.error(r.text)

        # --- Release / Consume ---
        st.markdown("### 释放/消耗（按 alloc_id）")
        c1, c2 = st.columns(2)
        alloc_id = c1.number_input("alloc_id", min_value=1, value=1, key="alloc_id_op")
        action_note = c2.text_input("动作备注", "", key="alloc_note_op")
        bc1, bc2 = st.columns(2)
        if bc1.button("释放", key="release"):
            r = api_post(f"/api/allocs/{int(alloc_id)}/release", json={"note": action_note})
            st.success("释放成功") if r.ok else st.error(r.text)
        if bc2.button("消耗", key="consume"):
            r = api_post(f"/api/allocs/{int(alloc_id)}/consume", json={"note": action_note})
            st.success("消耗成功") if r.ok else st.error(r.text)


# ---------------------------------------------------------------------------
# Tab: Project Resources
# ---------------------------------------------------------------------------
def render_resources_tab() -> None:
    st.subheader("项目资源管理")

    # Get projects for selection
    try:
        projects = api_get("/api/projects").json().get("items", [])
    except Exception:
        projects = []
    codes = [p["code"] for p in projects]
    code = st.selectbox("选择项目", options=[""] + codes, key="res_proj_sel")

    if not code:
        st.info("请先选择一个项目。")
        return

    # --- Resource list ---
    st.markdown("### 资源列表")
    try:
        rr = api_get(f"/api/projects/{code}/resources")
        if rr.ok:
            items = rr.json().get("items", [])
            if items:
                st.dataframe(items, use_container_width=True)
            else:
                st.info("该项目暂无资源。")
        else:
            st.error(rr.text)
    except Exception as exc:
        st.error(f"获取资源失败：{exc}")

    # --- Add resource ---
    st.markdown("### 新增/更新资源")
    with st.form("resource_add"):
        c1, c2 = st.columns(2)
        r_type = c1.selectbox("类型", ["doc", "schematic", "pcb", "firmware", "bom", "image", "url", "other"], key="res_type")
        name = c2.text_input("名称", "", key="res_name")
        uri = c1.text_input("路径/URL", "", key="res_uri")
        is_dir = c2.selectbox("是否目录", [0, 1], key="res_isdir")
        tags = c1.text_input("标签（逗号分隔）", "", key="res_tags")
        note = c2.text_input("备注", "", key="res_note")
        no_check = st.checkbox("跳过路径检查", key="res_nocheck")
        if st.form_submit_button("新增/更新资源"):
            r = api_post(f"/api/projects/{code}/resources", json={
                "type": r_type, "name": name, "uri": uri,
                "is_dir": is_dir, "tags": tags, "note": note, "no_check": no_check,
            })
            if r.ok:
                st.success("资源已保存")
                st.rerun()
            else:
                st.error(r.text)

    # --- Delete resource ---
    st.markdown("### 删除资源")
    with st.form("resource_del"):
        c1, c2 = st.columns(2)
        del_type = c1.text_input("删除用 type", key="del_res_type")
        del_uri = c2.text_input("删除用 uri", key="del_res_uri")
        if st.form_submit_button("删除资源"):
            r = api_delete(f"/api/projects/{code}/resources", json={"type": del_type, "uri": del_uri})
            if r.ok:
                st.success("删除完成")
                st.rerun()
            else:
                st.error(r.text)

    # --- Check resources ---
    if st.button("检查资源有效性", key="check_res"):
        r = api_post(f"/api/projects/{code}/resources/check")
        if r.ok:
            check_items = r.json().get("items", [])
            if check_items:
                st.dataframe(check_items, use_container_width=True)
            else:
                st.info("无资源需要检查。")
        else:
            st.error(r.text)


# ---------------------------------------------------------------------------
# Tab: LCSC Import
# ---------------------------------------------------------------------------
def render_lcsc_tab() -> None:
    st.subheader("立创商城 (LCSC) 元件导入")

    st.markdown("### 方式一：从立创网页 URL 导入")
    st.caption("输入立创商城元件详情页 URL，系统将自动抓取元件信息并写入数据库。")
    with st.form("lcsc_url_form"):
        url = st.text_input("立创商城 URL", "", placeholder="https://item.szlcsc.com/...")
        datasheets_dir = st.text_input("数据手册存放目录", "./datasheets")
        if st.form_submit_button("抓取并导入"):
            if not url:
                st.warning("请输入 URL")
            else:
                with st.spinner("正在抓取立创商城页面..."):
                    r = api_post("/api/lcsc/fetch", data={"url": url, "datasheets_dir": datasheets_dir})
                if r.ok:
                    st.success(r.json().get("detail", "导入成功"))
                else:
                    st.error(r.text)

    st.divider()
    st.markdown("### 方式二：从立创订单 XLSX 批量导入")
    st.caption("上传立创商城导出的订单 XLSX 文件，系统将批量导入元件和库存。")
    with st.form("lcsc_xlsx_form"):
        lcsc_file = st.file_uploader("选择立创订单 XLSX", type=["xlsx"], key="lcsc_xlsx")
        inbound_loc = st.text_input("入库库位", "LCSC-INBOX", key="lcsc_loc")
        if st.form_submit_button("批量导入"):
            if lcsc_file is None:
                st.warning("请选择文件")
            else:
                files = {"file": (lcsc_file.name, lcsc_file.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                r = api_post("/api/lcsc/import-xlsx", files=files, data={"inbound_location": inbound_loc})
                if r.ok:
                    result = r.json()
                    st.success(f"导入完成：元件 {result.get('ok', 0)} 条，库存 {result.get('err', 0)} 条")
                else:
                    st.error(r.text)


# ---------------------------------------------------------------------------
# Tab: Ledger
# ---------------------------------------------------------------------------
def render_ledger_tab() -> None:
    st.subheader("出入库台账 / 交易记录")

    c1, c2, c3 = st.columns(3)
    proj = c1.text_input("项目编码筛选", "", key="ledger_proj")
    mpn = c2.text_input("MPN 筛选", "", key="ledger_mpn")
    since = c3.date_input("起始日期", value=None, key="ledger_since")

    since_str = since.isoformat() if since else ""
    try:
        rows = api_get("/api/ledger", params={"project": proj, "mpn": mpn, "since": since_str}).json().get("items", [])
    except Exception as exc:
        st.error(f"查询台账失败：{exc}")
        rows = []
    if rows:
        st.dataframe(rows, use_container_width=True)
    else:
        st.info("暂无交易记录。")


# ---------------------------------------------------------------------------
# Tab: XLSX Import/Export
# ---------------------------------------------------------------------------
def render_xlsx_tab() -> None:
    st.subheader("XLSX 批量导入/导出")

    # --- Download template ---
    st.markdown("### 下载交易 XLSX 模板")
    st.caption("下载标准模板文件，填写后可批量导入出入库交易。")
    if st.button("下载模板", key="dl_tmpl"):
        r = api_get("/api/txns/export-template")
        if r.ok:
            st.download_button(
                label="点击下载 txn_template.xlsx",
                data=r.content,
                file_name="txn_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_btn",
            )
        else:
            st.error("生成模板失败")

    st.divider()

    # --- Import transactions ---
    st.markdown("### 导入交易 XLSX")
    st.caption("等价于 CLI 的 txn-import-xlsx，支持 Transactions / StockIn / StockOut sheet。")
    with st.form("txn_import_form"):
        txn_file = st.file_uploader("选择交易 XLSX", type=["xlsx"], key="txn_file")
        c1, c2 = st.columns(2)
        mode = c1.selectbox("导入模式", ["auto", "transactions", "stock-io"], key="txn_mode")
        partial = c2.checkbox("部分导入（遇到错误继续）", key="txn_partial")
        if st.form_submit_button("导入交易"):
            if txn_file is None:
                st.warning("请选择文件")
            else:
                files = {"file": (txn_file.name, txn_file.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                r = api_post("/api/txns/import-xlsx", files=files, data={"partial": str(partial).lower(), "mode": mode})
                if r.ok:
                    result = r.json()
                    st.success(f"导入结果：成功 {result.get('ok', 0)} 条，失败 {result.get('err', 0)} 条")
                else:
                    st.error(r.text)

    st.divider()

    # --- Import resources XLSX ---
    st.markdown("### 导入项目资源 XLSX")
    st.caption("从 XLSX 批量导入项目资源记录。")
    with st.form("res_import_form"):
        res_file = st.file_uploader("选择资源 XLSX", type=["xlsx"], key="res_file")
        c1, c2 = st.columns(2)
        sheet = c1.text_input("Sheet 名称", "Resources", key="res_sheet")
        header_row = c2.number_input("表头行号", min_value=1, value=1, key="res_header")
        c3, c4 = st.columns(2)
        no_check = c3.checkbox("跳过路径检查", key="res_import_nocheck")
        auto_create = c4.checkbox("自动创建不存在的项目", key="res_auto_create")
        if st.form_submit_button("导入资源"):
            if res_file is None:
                st.warning("请选择文件")
            else:
                files = {"file": (res_file.name, res_file.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                r = api_post(
                    "/api/projects/resources/import-xlsx",
                    files=files,
                    data={
                        "sheet": sheet, "header_row": int(header_row),
                        "no_check": str(no_check).lower(), "auto_create_project": str(auto_create).lower(),
                    },
                )
                if r.ok:
                    result = r.json()
                    st.success(f"导入结果：成功 {result.get('ok', 0)} 条，失败 {result.get('err', 0)} 条")
                else:
                    st.error(r.text)


# ---------------------------------------------------------------------------
# Tab: Locations
# ---------------------------------------------------------------------------
def render_locations_tab() -> None:
    st.subheader("库位管理")
    try:
        locs = api_get("/api/locations").json().get("items", [])
    except Exception as exc:
        st.error(f"获取库位失败：{exc}")
        locs = []
    if locs:
        st.dataframe(locs, use_container_width=True)
        st.caption(f"共 {len(locs)} 个库位")
    else:
        st.info("暂无库位信息。请通过 CLI 执行 init-locations 初始化库位。")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="实验室库存系统", layout="wide")
    st.title("实验室库存与项目管理")

    render_sidebar()

    tab_parts, tab_stock_ops, tab_project, tab_resources, tab_lcsc, tab_ledger, tab_xlsx, tab_locations = st.tabs([
        "元件与库存",
        "出入库操作",
        "项目管理",
        "项目资源",
        "立创导入",
        "交易台账",
        "XLSX 导入/导出",
        "库位管理",
    ])

    with tab_parts:
        render_parts_stock_tab()
    with tab_stock_ops:
        render_stock_ops_tab()
    with tab_project:
        render_project_tab()
    with tab_resources:
        render_resources_tab()
    with tab_lcsc:
        render_lcsc_tab()
    with tab_ledger:
        render_ledger_tab()
    with tab_xlsx:
        render_xlsx_tab()
    with tab_locations:
        render_locations_tab()


if __name__ == "__main__":
    main()
