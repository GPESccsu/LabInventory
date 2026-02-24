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


def _show_api_error(r):
    """Display a user-friendly API error."""
    try:
        detail = r.json().get("detail", r.text)
    except Exception:
        detail = r.text
    st.error(f"操作失败：{detail}")


def main() -> None:
    st.set_page_config(page_title="实验室库存系统", layout="wide")
    st.title("实验室库存与项目管理")

    # Sidebar: system info
    with st.sidebar:
        st.caption(f"API 地址：{API_BASE}")
        try:
            h = api_get("/api/health").json()
            st.metric("物料种类", h.get("parts_count", "?"))
            st.metric("有库存记录", h.get("stock_rows", "?"))
            st.metric("项目数", h.get("projects_count", "?"))
        except Exception:
            st.warning("无法连接 API，请确认后端已启动")

    tab_stock, tab_parts, tab_projects, tab_resources, tab_ledger, tab_import = st.tabs(
        ["库存管理", "物料查询", "项目管理", "项目资源", "库存流水", "XLSX 导入"]
    )

    # ===== Tab 1: Stock Management =====
    with tab_stock:
        st.subheader("库存查询")
        col_q, col_loc = st.columns(2)
        stock_query = col_q.text_input("搜索物料（MPN/名称）", "", key="stock_q")
        stock_loc = col_loc.text_input("按库位筛选", "", key="stock_loc")
        try:
            stock_rows = api_get("/api/stock", params={"query": stock_query, "location": stock_loc}).json().get("items", [])
        except Exception as exc:
            st.error(f"查询库存失败：{exc}")
            stock_rows = []
        if stock_rows:
            st.dataframe(stock_rows, use_container_width=True, hide_index=True)
        else:
            st.info("暂无库存记录" if not stock_query else "未找到匹配的库存记录")

        st.divider()
        st.subheader("库存操作")
        op = st.radio("操作类型", ["入库", "出库", "移库", "调整"], horizontal=True, key="stock_op")

        if op == "入库":
            with st.form("stock_in_form"):
                c1, c2, c3 = st.columns(3)
                si_mpn = c1.text_input("MPN", key="si_mpn")
                si_loc = c2.text_input("库位", key="si_loc")
                si_qty = c3.number_input("数量", min_value=1, value=1, key="si_qty")
                c4, c5 = st.columns(2)
                si_cond = c4.text_input("状态", value="new", key="si_cond")
                si_note = c5.text_input("备注", "", key="si_note")
                if st.form_submit_button("执行入库"):
                    r = api_post("/api/stock/in", json={"mpn": si_mpn, "location": si_loc, "qty": int(si_qty), "condition": si_cond, "note": si_note})
                    if r.ok:
                        st.success(r.json().get("detail", "入库成功"))
                    else:
                        _show_api_error(r)

        elif op == "出库":
            with st.form("stock_out_form"):
                c1, c2, c3 = st.columns(3)
                so_mpn = c1.text_input("MPN", key="so_mpn")
                so_loc = c2.text_input("库位", key="so_loc")
                so_qty = c3.number_input("数量", min_value=1, value=1, key="so_qty")
                c4, c5 = st.columns(2)
                so_proj = c4.text_input("项目编码（可选）", "", key="so_proj")
                so_note = c5.text_input("备注", "", key="so_note")
                c6, c7 = st.columns(2)
                so_ref = c6.text_input("参考号", "", key="so_ref")
                so_op = c7.text_input("操作人", "", key="so_operator")
                if st.form_submit_button("执行出库"):
                    r = api_post("/api/stock/out", json={"mpn": so_mpn, "location": so_loc, "qty": int(so_qty), "project_code": so_proj, "ref": so_ref, "note": so_note, "operator": so_op})
                    if r.ok:
                        st.success(r.json().get("detail", "出库成功"))
                    else:
                        _show_api_error(r)

        elif op == "移库":
            with st.form("stock_move_form"):
                c1, c2 = st.columns(2)
                sm_mpn = c1.text_input("MPN", key="sm_mpn")
                sm_qty = c2.number_input("数量", min_value=1, value=1, key="sm_qty")
                c3, c4 = st.columns(2)
                sm_from = c3.text_input("源库位", key="sm_from")
                sm_to = c4.text_input("目标库位", key="sm_to")
                c5, c6 = st.columns(2)
                sm_note = c5.text_input("备注", "", key="sm_note")
                sm_op = c6.text_input("操作人", "", key="sm_operator")
                if st.form_submit_button("执行移库"):
                    r = api_post("/api/stock/move", json={"mpn": sm_mpn, "from_location": sm_from, "to_location": sm_to, "qty": int(sm_qty), "note": sm_note, "operator": sm_op})
                    if r.ok:
                        st.success(r.json().get("detail", "移库成功"))
                    else:
                        _show_api_error(r)

        elif op == "调整":
            with st.form("stock_adjust_form"):
                c1, c2, c3 = st.columns(3)
                sa_mpn = c1.text_input("MPN", key="sa_mpn")
                sa_loc = c2.text_input("库位", key="sa_loc")
                sa_dir = c3.selectbox("方向", ["增加", "减少"], key="sa_dir")
                c4, c5 = st.columns(2)
                sa_qty = c4.number_input("数量", min_value=1, value=1, key="sa_qty")
                sa_note = c5.text_input("原因（必填）", key="sa_note")
                c6, c7 = st.columns(2)
                sa_ref = c6.text_input("参考号", "", key="sa_ref")
                sa_op = c7.text_input("操作人", "", key="sa_operator")
                if st.form_submit_button("执行调整"):
                    payload = {
                        "mpn": sa_mpn, "location": sa_loc,
                        "add_qty": int(sa_qty) if sa_dir == "增加" else 0,
                        "sub_qty": int(sa_qty) if sa_dir == "减少" else 0,
                        "note": sa_note, "ref": sa_ref, "operator": sa_op,
                    }
                    r = api_post("/api/stock/adjust", json=payload)
                    if r.ok:
                        st.success(r.json().get("detail", "调整成功"))
                    else:
                        _show_api_error(r)

    # ===== Tab 2: Parts Search =====
    with tab_parts:
        st.subheader("物料查询")
        parts_q = st.text_input("搜索（MPN/名称/类别/封装）", "", key="parts_q")
        try:
            parts = api_get("/api/parts", params={"query": parts_q}).json().get("items", [])
        except Exception as exc:
            st.error(f"查询物料失败：{exc}")
            parts = []
        if parts:
            st.dataframe(parts, use_container_width=True, hide_index=True)
            st.caption(f"共 {len(parts)} 条记录（最多显示 200 条）")
        else:
            st.info("暂无物料记录" if not parts_q else "未找到匹配的物料")

    # ===== Tab 3: Project Management =====
    with tab_projects:
        st.subheader("项目列表与创建")
        q = st.text_input("搜索项目（code/name/owner）", "", key="proj_q")
        try:
            projects = api_get("/api/projects", params={"query": q}).json().get("items", [])
        except Exception as exc:
            st.error(f"读取项目失败：{exc}")
            projects = []
        if projects:
            st.dataframe(projects, use_container_width=True, hide_index=True)
        else:
            st.info("暂无项目")

        with st.form("create_project"):
            st.markdown("**创建/更新项目**")
            c1, c2 = st.columns(2)
            code = c1.text_input("项目编码", "", key="cp_code")
            name = c2.text_input("项目名称", "", key="cp_name")
            owner = c1.text_input("负责人", "", key="cp_owner")
            note = c2.text_input("备注", "", key="cp_note")
            if st.form_submit_button("创建/更新项目"):
                r = api_post("/api/projects", json={"code": code, "name": name, "owner": owner, "note": note})
                if r.ok:
                    st.success("项目已保存")
                else:
                    _show_api_error(r)

        st.divider()
        codes = [p["code"] for p in projects]
        selected = st.selectbox("选择项目查看详情", options=codes, key="proj_sel") if codes else ""
        if selected:
            st.markdown("### 项目状态（BOM + 库存 + 预留）")
            try:
                status_rows = api_get(f"/api/projects/{selected}/status").json().get("items", [])
            except Exception:
                status_rows = []
            if status_rows:
                st.dataframe(status_rows, use_container_width=True, hide_index=True)
            else:
                st.info("该项目无 BOM 记录")

            st.markdown("### 预留明细")
            try:
                alloc_rows = api_get(f"/api/projects/{selected}/allocs").json().get("items", [])
            except Exception:
                alloc_rows = []
            if alloc_rows:
                st.dataframe(alloc_rows, use_container_width=True, hide_index=True)
            else:
                st.info("该项目无预留记录")

            with st.form("reserve_form"):
                st.markdown("**执行预留**")
                c1, c2, c3 = st.columns(3)
                mpn = c1.text_input("MPN", key="rv_mpn")
                location = c2.text_input("库位", key="rv_loc")
                qty = c3.number_input("预留数量", min_value=1, value=1, key="rv_qty")
                note = st.text_input("备注", "", key="rv_note")
                if st.form_submit_button("执行预留"):
                    r = api_post(f"/api/projects/{selected}/reserve", json={"mpn": mpn, "location": location, "qty": int(qty), "note": note})
                    if r.ok:
                        st.success(f"预留成功：alloc_id={r.json()['alloc_id']}")
                    else:
                        _show_api_error(r)

            st.markdown("### 释放/消耗（按 alloc_id）")
            c1, c2 = st.columns(2)
            alloc_id = c1.number_input("alloc_id", min_value=1, value=1, key="alloc_id")
            action_note = c2.text_input("动作备注", "", key="action_note")
            bc1, bc2 = st.columns(2)
            if bc1.button("释放", key="release"):
                r = api_post(f"/api/allocs/{int(alloc_id)}/release", json={"note": action_note})
                if r.ok:
                    st.success("释放成功")
                else:
                    _show_api_error(r)
            if bc2.button("消耗", key="consume"):
                r = api_post(f"/api/allocs/{int(alloc_id)}/consume", json={"note": action_note})
                if r.ok:
                    st.success("消耗成功")
                else:
                    _show_api_error(r)

    # ===== Tab 4: Project Resources =====
    with tab_resources:
        st.subheader("项目资源")
        code = st.text_input("项目编码（资源操作）", "", key="res_code")
        if code:
            with st.form("resource_add"):
                st.markdown("**新增/更新资源**")
                c1, c2 = st.columns(2)
                r_type = c1.text_input("类型(type)", "doc", key="ra_type")
                name = c2.text_input("名称(name)", "", key="ra_name")
                uri = c1.text_input("路径/URL(uri)", "", key="ra_uri")
                is_dir = c2.selectbox("是否目录", [1, 0], key="ra_isdir")
                tags = c1.text_input("标签(tags)", "", key="ra_tags")
                note = c2.text_input("备注(note)", "", key="ra_note")
                no_check = st.checkbox("跳过路径检查", key="ra_nocheck")
                if st.form_submit_button("新增/更新资源"):
                    r = api_post(f"/api/projects/{code}/resources", json={"type": r_type, "name": name, "uri": uri, "is_dir": is_dir, "tags": tags, "note": note, "no_check": no_check})
                    if r.ok:
                        st.success("资源已保存")
                    else:
                        _show_api_error(r)

            if st.button("刷新资源列表", key="refresh_res"):
                pass
            rr = api_get(f"/api/projects/{code}/resources")
            if rr.ok:
                items = rr.json().get("items", [])
                if items:
                    st.dataframe(items, use_container_width=True, hide_index=True)
                else:
                    st.info("该项目暂无资源")
            else:
                _show_api_error(rr)

            st.markdown("#### 删除资源")
            c1, c2 = st.columns(2)
            del_type = c1.text_input("删除用 type", key="del_type")
            del_uri = c2.text_input("删除用 uri", key="del_uri")
            if st.button("删除资源", key="del_res"):
                r = api_delete(f"/api/projects/{code}/resources", json={"type": del_type, "uri": del_uri})
                if r.ok:
                    st.success("删除完成")
                else:
                    _show_api_error(r)

            if st.button("检查资源有效性", key="check_res"):
                r = api_post(f"/api/projects/{code}/resources/check")
                if r.ok:
                    check_items = r.json().get("items", [])
                    if check_items:
                        st.dataframe(check_items, use_container_width=True, hide_index=True)
                    else:
                        st.info("该项目暂无资源可检查")
                else:
                    _show_api_error(r)

    # ===== Tab 5: Ledger =====
    with tab_ledger:
        st.subheader("库存流水查询")
        c1, c2, c3 = st.columns(3)
        lg_proj = c1.text_input("按项目筛选", "", key="lg_proj")
        lg_mpn = c2.text_input("按 MPN 筛选", "", key="lg_mpn")
        lg_since = c3.text_input("起始日期（YYYY-MM-DD）", "", key="lg_since")
        try:
            ledger_rows = api_get("/api/ledger", params={"project": lg_proj, "mpn": lg_mpn, "since": lg_since}).json().get("items", [])
        except Exception as exc:
            st.error(f"查询流水失败：{exc}")
            ledger_rows = []
        if ledger_rows:
            st.dataframe(ledger_rows, use_container_width=True, hide_index=True)
            st.caption(f"共 {len(ledger_rows)} 条记录（最多显示 500 条）")
        else:
            st.info("暂无流水记录")

    # ===== Tab 6: XLSX Import =====
    with tab_import:
        st.subheader("XLSX 批量导入")

        st.markdown("#### 交易导入")
        txn_file = st.file_uploader("选择交易 XLSX 文件", type=["xlsx"], key="txn")
        c1, c2 = st.columns(2)
        txn_mode = c1.selectbox("导入模式", ["auto", "transactions", "stock-io"], key="txn_mode")
        txn_partial = c2.checkbox("部分成功模式", key="txn_partial")
        if st.button("导入交易 XLSX", key="btn_txn") and txn_file is not None:
            files = {"file": (txn_file.name, txn_file.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            r = api_post("/api/txns/import-xlsx", files=files, data={"partial": str(txn_partial).lower(), "mode": txn_mode})
            if r.ok:
                result = r.json()
                st.success(f"导入结果：成功 {result.get('ok', 0)} 行，失败 {result.get('err', 0)} 行")
            else:
                _show_api_error(r)

        st.divider()
        st.markdown("#### 项目资源导入")
        res_file = st.file_uploader("选择项目资源 XLSX 文件", type=["xlsx"], key="res")
        c1, c2 = st.columns(2)
        res_auto_create = c1.checkbox("自动创建项目", key="res_auto")
        res_no_check = c2.checkbox("跳过路径检查", key="res_nocheck_import")
        if st.button("导入资源 XLSX", key="btn_res") and res_file is not None:
            files = {"file": (res_file.name, res_file.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            r = api_post(
                "/api/projects/resources/import-xlsx",
                files=files,
                data={"sheet": "Resources", "header_row": 1, "no_check": str(res_no_check).lower(), "auto_create_project": str(res_auto_create).lower()},
            )
            if r.ok:
                result = r.json()
                st.success(f"导入结果：成功 {result.get('ok', 0)} 行，失败 {result.get('err', 0)} 行")
            else:
                _show_api_error(r)


if __name__ == "__main__":
    main()
