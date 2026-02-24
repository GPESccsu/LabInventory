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


def main() -> None:
    st.set_page_config(page_title="实验室库存系统", layout="wide")
    st.title("实验室库存与项目管理")
    st.caption(f"API 地址：{API_BASE}")

    tab1, tab2, tab3 = st.tabs(["项目管理", "项目资源", "XLSX 导入"]) 

    with tab1:
        st.subheader("项目列表与创建")
        q = st.text_input("搜索项目（code/name/owner）", "")
        try:
            projects = api_get("/api/projects", params={"query": q}).json().get("items", [])
        except Exception as exc:
            st.error(f"读取项目失败：{exc}")
            projects = []
        st.dataframe(projects, use_container_width=True)

        with st.form("create_project"):
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

        codes = [p["code"] for p in projects]
        selected = st.selectbox("选择项目", options=codes) if codes else ""
        if selected:
            st.markdown("### 项目状态（BOM + 库存 + 预留）")
            status_rows = api_get(f"/api/projects/{selected}/status").json().get("items", [])
            st.dataframe(status_rows, use_container_width=True)

            st.markdown("### 预留明细")
            alloc_rows = api_get(f"/api/projects/{selected}/allocs").json().get("items", [])
            st.dataframe(alloc_rows, use_container_width=True)

            with st.form("reserve_form"):
                mpn = st.text_input("MPN")
                location = st.text_input("库位")
                qty = st.number_input("预留数量", min_value=1, value=1)
                note = st.text_input("备注", "")
                if st.form_submit_button("执行预留"):
                    r = api_post(f"/api/projects/{selected}/reserve", json={"mpn": mpn, "location": location, "qty": int(qty), "note": note})
                    if r.ok:
                        st.success(f"预留成功：alloc_id={r.json()['alloc_id']}")
                    else:
                        st.error(r.text)

            st.markdown("### 释放/消耗（按 alloc_id）")
            c1, c2 = st.columns(2)
            alloc_id = c1.number_input("alloc_id", min_value=1, value=1)
            action_note = c2.text_input("动作备注", "")
            if st.button("释放", key="release"):
                r = api_post(f"/api/allocs/{int(alloc_id)}/release", json={"note": action_note})
                st.success("释放成功") if r.ok else st.error(r.text)
            if st.button("消耗", key="consume"):
                r = api_post(f"/api/allocs/{int(alloc_id)}/consume", json={"note": action_note})
                st.success("消耗成功") if r.ok else st.error(r.text)

    with tab2:
        st.subheader("项目资源")
        code = st.text_input("项目编码（资源操作）", "")
        if code:
            with st.form("resource_add"):
                c1, c2 = st.columns(2)
                r_type = c1.text_input("类型(type)", "doc")
                name = c2.text_input("名称(name)", "")
                uri = c1.text_input("路径/URL(uri)", "")
                is_dir = c2.selectbox("是否目录", [1, 0])
                tags = c1.text_input("标签(tags)", "")
                note = c2.text_input("备注(note)", "")
                no_check = st.checkbox("跳过路径检查")
                if st.form_submit_button("新增/更新资源"):
                    r = api_post(f"/api/projects/{code}/resources", json={"type": r_type, "name": name, "uri": uri, "is_dir": is_dir, "tags": tags, "note": note, "no_check": no_check})
                    st.success("资源已保存") if r.ok else st.error(r.text)

            if st.button("刷新资源列表"):
                pass
            rr = api_get(f"/api/projects/{code}/resources")
            if rr.ok:
                items = rr.json().get("items", [])
                st.dataframe(items, use_container_width=True)
            else:
                st.error(rr.text)

            st.markdown("#### 删除资源")
            del_type = st.text_input("删除用 type")
            del_uri = st.text_input("删除用 uri")
            if st.button("删除资源"):
                r = api_delete(f"/api/projects/{code}/resources", json={"type": del_type, "uri": del_uri})
                st.success("删除完成") if r.ok else st.error(r.text)

            if st.button("检查资源有效性"):
                r = api_post(f"/api/projects/{code}/resources/check")
                if r.ok:
                    st.dataframe(r.json().get("items", []), use_container_width=True)
                else:
                    st.error(r.text)

    with tab3:
        st.subheader("XLSX 批量导入")
        txn_file = st.file_uploader("导入交易 XLSX（等价 txn-import-xlsx）", type=["xlsx"], key="txn")
        if st.button("导入交易 XLSX") and txn_file is not None:
            files = {"file": (txn_file.name, txn_file.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            r = api_post("/api/txns/import-xlsx", files=files, data={"partial": "false", "mode": "auto"})
            st.success(f"导入结果：{r.json()}") if r.ok else st.error(r.text)

        res_file = st.file_uploader("导入项目资源 XLSX", type=["xlsx"], key="res")
        if st.button("导入资源 XLSX") and res_file is not None:
            files = {"file": (res_file.name, res_file.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            r = api_post(
                "/api/projects/resources/import-xlsx",
                files=files,
                data={"sheet": "Resources", "header_row": 1, "no_check": "false", "auto_create_project": "false"},
            )
            st.success(f"导入结果：{r.json()}") if r.ok else st.error(r.text)


if __name__ == "__main__":
    main()
