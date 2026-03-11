from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

from backend.app import inv
from backend.app.db import connect, init_db
from backend.app.project_resources import check_resources, import_resources_xlsx, list_resources, remove_resource, upsert_resource


class InventoryError(RuntimeError):
    pass


class DatabaseLockedError(InventoryError):
    pass


class NotFoundError(InventoryError):
    pass


def _normalize_error(exc: Exception) -> Exception:
    """Convert low-level exceptions into the InventoryError hierarchy."""
    if isinstance(exc, InventoryError):
        return exc
    msg = str(exc).lower()
    if isinstance(exc, sqlite3.OperationalError) and "database is locked" in msg:
        return DatabaseLockedError("数据库被锁定，请关闭占用数据库的程序后重试。")
    if "不存在" in msg:
        return NotFoundError(str(exc))
    return InventoryError(str(exc))


class InventoryService:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def _conn(self) -> sqlite3.Connection:
        conn = connect(self.db_path)
        init_db(conn)
        return conn

    # --- Projects ---

    def upsert_project(self, code: str, name: str, owner: str = "", note: str = "") -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    project_id, created = inv.add_project(conn, code=code, name=name, owner=owner, note=note)
                row = conn.execute("SELECT id, code, name, owner, status, note, created_at FROM projects WHERE id=?", (project_id,)).fetchone()
                return dict(row)
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def list_projects(self, query: str = "") -> list[dict[str, Any]]:
        try:
            with closing(self._conn()) as conn:
                if query:
                    rows = conn.execute(
                        """
                        SELECT id, code, name, owner, status, note, created_at
                        FROM projects
                        WHERE code LIKE ? OR name LIKE ? OR owner LIKE ?
                        ORDER BY code
                        """,
                        (f"%{query}%", f"%{query}%", f"%{query}%"),
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT id, code, name, owner, status, note, created_at FROM projects ORDER BY code").fetchall()
                return [dict(r) for r in rows]
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def get_project(self, code: str) -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                row = conn.execute("SELECT id, code, name, owner, status, note, created_at FROM projects WHERE code=?", (code,)).fetchone()
                if not row:
                    raise NotFoundError(f"项目不存在：{code}")
                return dict(row)
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def get_project_status(self, code: str) -> list[dict[str, Any]]:
        try:
            with closing(self._conn()) as conn:
                rows = conn.execute(
                    "SELECT * FROM v_project_material_status WHERE project_code=? ORDER BY mpn",
                    (code,),
                ).fetchall()
                return [dict(r) for r in rows]
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def get_project_allocs(self, code: str) -> list[dict[str, Any]]:
        try:
            with closing(self._conn()) as conn:
                rows = conn.execute(
                    """
                    SELECT a.id AS alloc_id, pr.code AS project_code, p.mpn, p.name AS part_desc,
                           a.location, a.alloc_qty, a.status, a.note, a.updated_at
                    FROM project_alloc a
                    JOIN projects pr ON pr.id=a.project_id
                    JOIN parts p ON p.id=a.part_id
                    WHERE pr.code=?
                    ORDER BY a.id DESC
                    """,
                    (code,),
                ).fetchall()
                return [dict(r) for r in rows]
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def set_project_bom(self, code: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    for item in items:
                        inv.set_bom(
                            conn,
                            project_code=code,
                            mpn=item["mpn"],
                            req_qty=int(item["req_qty"]),
                            priority=int(item.get("priority", 2)),
                            note=item.get("note", ""),
                        )
            return {"project_code": code, "updated": len(items)}
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def reserve(self, code: str, mpn: str, location: str, qty: int, note: str = "") -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    alloc_id = inv.reserve_loc(conn, code, mpn, location, qty, note)
            return {"alloc_id": alloc_id, "project_code": code}
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def release_alloc(self, alloc_id: int, note: str = "释放") -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    inv.release_alloc(conn, alloc_id, note_append=note or "释放")
            return {"alloc_id": alloc_id, "status": "released"}
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def consume_alloc(self, alloc_id: int, note: str = "已消耗") -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    inv.consume_alloc(conn, alloc_id, note_append=note or "已消耗")
            return {"alloc_id": alloc_id, "status": "consumed"}
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    # --- Resources ---

    def upsert_resource(
        self,
        project_code: str,
        resource_type: str,
        name: str,
        uri: str,
        is_dir: int = 1,
        tags: str = "",
        note: str = "",
        no_check: bool = False,
    ) -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    project_id = inv.get_project_id(conn, project_code)
                    resource_id = upsert_resource(
                        conn,
                        project_id=project_id,
                        resource_type=resource_type,
                        name=name,
                        uri=uri,
                        is_dir=is_dir,
                        tags=tags,
                        note=note,
                        no_check=no_check,
                    )
            return {"id": resource_id}
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def list_resources(self, project_code: str) -> list[dict[str, Any]]:
        try:
            with closing(self._conn()) as conn:
                project_id = inv.get_project_id(conn, project_code)
                return [dict(r) for r in list_resources(conn, project_id)]
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def delete_resource(self, project_code: str, resource_type: str, uri: str) -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    project_id = inv.get_project_id(conn, project_code)
                    deleted = remove_resource(conn, project_id, resource_type, uri)
            return {"deleted": deleted}
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def check_resource(self, project_code: str) -> list[dict[str, Any]]:
        try:
            with closing(self._conn()) as conn:
                project_id = inv.get_project_id(conn, project_code)
                return check_resources(conn, project_id)
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    # --- XLSX Import ---

    def import_resource_xlsx(self, xlsx_bytes: bytes, *, sheet: str = "Resources", header_row: int = 1, no_check: bool = False, auto_create_project: bool = False) -> dict[str, Any]:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        tmp.write(xlsx_bytes)
        tmp.close()
        try:
            with closing(self._conn()) as conn:
                with conn:
                    ok, err = import_resources_xlsx(
                        conn,
                        xlsx_path=Path(tmp.name),
                        sheet=sheet,
                        header_row=header_row,
                        no_check=no_check,
                        auto_create_project=auto_create_project,
                        get_project_id=lambda code: inv.get_project_id(conn, code),
                        create_project=lambda code, name: inv.create_project(conn, code, name),
                    )
            return {"ok": ok, "err": err}
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def import_txn_xlsx(self, xlsx_bytes: bytes, *, partial: bool = False, mode: str = "auto") -> dict[str, Any]:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        tmp.write(xlsx_bytes)
        tmp.close()
        try:
            with closing(self._conn()) as conn:
                with conn:
                    ok, err = inv.txn_import_xlsx(conn, Path(tmp.name), partial=partial, mode=mode)
            return {"ok": ok, "err": err}
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    # --- Parts & Stock ---

    def search_parts(self, query: str = "") -> list[dict[str, Any]]:
        try:
            with closing(self._conn()) as conn:
                if query:
                    like = f"%{query}%"
                    rows = conn.execute(
                        """
                        SELECT id, mpn, name, category, package, params, unit, url, datasheet, note, created_at
                        FROM parts
                        WHERE mpn LIKE ? OR name LIKE ? OR category LIKE ? OR package LIKE ?
                        ORDER BY mpn
                        LIMIT 200
                        """,
                        (like, like, like, like),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id, mpn, name, category, package, params, unit, url, datasheet, note, created_at FROM parts ORDER BY mpn LIMIT 200"
                    ).fetchall()
                return [dict(r) for r in rows]
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def list_stock(self, query: str = "", location: str = "") -> list[dict[str, Any]]:
        try:
            with closing(self._conn()) as conn:
                sql = """
                    SELECT s.id AS stock_id, s.part_id, p.mpn, p.name AS part_name,
                           s.location, s.qty, s.condition, s.updated_at
                    FROM stock s
                    JOIN parts p ON p.id = s.part_id
                    WHERE s.qty > 0
                """
                params: list[Any] = []
                if query:
                    like = f"%{query}%"
                    sql += " AND (p.mpn LIKE ? OR p.name LIKE ?)"
                    params.extend([like, like])
                if location:
                    sql += " AND s.location LIKE ?"
                    params.append(f"%{location}%")
                sql += " ORDER BY s.location, p.mpn LIMIT 500"
                rows = conn.execute(sql, tuple(params)).fetchall()
                return [dict(r) for r in rows]
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def list_locations(self) -> list[dict[str, Any]]:
        try:
            with closing(self._conn()) as conn:
                rows = conn.execute("SELECT location, note FROM locations ORDER BY location").fetchall()
                return [dict(r) for r in rows]
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def stock_in(self, mpn: str, location: str, qty: int, condition: str = "new", note: str = "") -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    inv.stock_in(conn, mpn, location, qty, condition=condition, note=note)
            return {"mpn": mpn, "location": location, "qty": qty}
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def stock_out(self, mpn: str, location: str, qty: int, project_code: str = "", ref: str = "", note: str = "", operator: str = "") -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    inv.stock_out(conn, mpn, location, qty, project_code=project_code, ref=ref, note=note, operator=operator)
            return {"mpn": mpn, "location": location, "qty": qty}
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def stock_move(self, mpn: str, from_location: str, to_location: str, qty: int, note: str = "", operator: str = "") -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    inv.stock_move(conn, mpn, from_location, to_location, qty, note=note, operator=operator)
            return {"mpn": mpn, "from_location": from_location, "to_location": to_location, "qty": qty}
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def stock_adjust(self, mpn: str, location: str, add_qty: int = 0, sub_qty: int = 0, note: str = "", ref: str = "", operator: str = "") -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    inv.stock_adjust(conn, mpn, location, add_qty=add_qty, sub_qty=sub_qty, note=note, ref=ref, operator=operator)
            return {"mpn": mpn, "location": location, "add_qty": add_qty, "sub_qty": sub_qty}
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def query_ledger(self, project_code: str = "", mpn: str = "", since: str = "") -> list[dict[str, Any]]:
        try:
            with closing(self._conn()) as conn:
                sql = """
                    SELECT d.created_at, d.doc_type, pr.code AS project_code, p.mpn,
                           d.from_location, d.to_location, l.qty, d.ref, d.operator, d.note
                    FROM inv_doc d
                    JOIN inv_line l ON l.doc_id = d.id
                    JOIN parts p ON p.id = l.part_id
                    LEFT JOIN projects pr ON pr.id = d.project_id
                    WHERE 1=1
                """
                params: list[Any] = []
                if project_code:
                    sql += " AND pr.code = ?"
                    params.append(project_code)
                if mpn:
                    sql += " AND p.mpn = ?"
                    params.append(mpn)
                if since:
                    sql += " AND date(d.created_at) >= date(?)"
                    params.append(since)
                sql += " ORDER BY d.id DESC LIMIT 500"
                rows = conn.execute(sql, tuple(params)).fetchall()
                return [dict(r) for r in rows]
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def health(self) -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                parts = conn.execute("SELECT COUNT(*) AS c FROM parts").fetchone()["c"]
                stock = conn.execute("SELECT COUNT(*) AS c FROM stock WHERE qty > 0").fetchone()["c"]
                projects = conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"]
                return {
                    "status": "ok",
                    "version": "1.0.0",
                    "db_path": str(self.db_path),
                    "parts_count": parts,
                    "stock_rows": stock,
                    "projects_count": projects,
                }
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    # --- LCSC ---

    def lcsc_fetch(self, url: str, datasheets_dir: str = "./datasheets") -> dict[str, Any]:
        """Fetch part info from an LCSC URL and upsert into parts table."""
        try:
            ds_dir = Path(datasheets_dir)
            ds_dir.mkdir(parents=True, exist_ok=True)
            item = inv.lcsc_fetch_and_parse(url, ds_dir)
            with closing(self._conn()) as conn:
                with conn:
                    part_id = inv.upsert_part(
                        conn,
                        mpn=item.mpn,
                        name=item.desc,
                        category=item.category,
                        package=item.package,
                        params=item.params_text,
                        url=item.page_url,
                        datasheet=item.datasheet_local or item.page_url,
                        note=item.note,
                    )
            return {
                "part_id": part_id,
                "mpn": item.mpn,
                "desc": item.desc,
                "category": item.category,
                "package": item.package,
                "lcsc_code": item.lcsc_code,
                "params_text": item.params_text,
                "page_url": item.page_url,
                "datasheet_local": item.datasheet_local,
            }
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc

    def lcsc_import_file(self, xlsx_bytes: bytes, inbound_location: str = "LCSC-INBOX") -> dict[str, Any]:
        """Import LCSC order XLSX into parts+stock."""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        tmp.write(xlsx_bytes)
        tmp.close()
        try:
            with closing(self._conn()) as conn:
                with conn:
                    ds_dir = Path(conn.execute("PRAGMA database_list").fetchone()[2]).parent / "datasheets"
                    part_written, stock_written = inv.import_lcsc_file_to_parts_and_stock(
                        conn,
                        lcsc_file=Path(tmp.name),
                        inbound_location=inbound_location,
                        datasheets_dir=ds_dir,
                    )
            return {"parts": part_written, "stock": stock_written}
        except InventoryError:
            raise
        except Exception as exc:
            raise _normalize_error(exc) from exc
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def txn_export_xlsx_template(self) -> bytes:
        """Generate a transaction XLSX template and return bytes."""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        tmp.close()
        try:
            inv.txn_export_xlsx_template(Path(tmp.name))
            return Path(tmp.name).read_bytes()
        finally:
            Path(tmp.name).unlink(missing_ok=True)

