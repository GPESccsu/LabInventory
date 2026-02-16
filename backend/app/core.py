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
    if isinstance(exc, sqlite3.OperationalError) and "database is locked" in str(exc).lower():
        return DatabaseLockedError("数据库被锁定，请关闭占用数据库的程序后重试。")
    return exc


class InventoryService:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def _conn(self):
        conn = connect(self.db_path)
        init_db(conn)
        return conn

    def upsert_project(self, code: str, name: str, owner: str = "", note: str = "") -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    project_id, created = inv.add_project(conn, code=code, name=name, owner=owner, note=note)
                row = conn.execute("SELECT id, code, name, owner, status, note, created_at FROM projects WHERE id=?", (project_id,)).fetchone()
                return dict(row)
        except Exception as exc:
            raise _normalize_error(exc)

    def list_projects(self, query: str = "") -> list[dict[str, Any]]:
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

    def get_project(self, code: str) -> dict[str, Any]:
        with closing(self._conn()) as conn:
            row = conn.execute("SELECT id, code, name, owner, status, note, created_at FROM projects WHERE code=?", (code,)).fetchone()
            if not row:
                raise NotFoundError(f"项目不存在：{code}")
            return dict(row)

    def get_project_status(self, code: str) -> list[dict[str, Any]]:
        with closing(self._conn()) as conn:
            rows = conn.execute(
                "SELECT * FROM v_project_material_status WHERE project_code=? ORDER BY mpn",
                (code,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_project_allocs(self, code: str) -> list[dict[str, Any]]:
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
        except Exception as exc:
            raise _normalize_error(exc)

    def reserve(self, code: str, mpn: str, location: str, qty: int, note: str = "") -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    alloc_id = inv.reserve_loc(conn, code, mpn, location, qty, note)
            return {"alloc_id": alloc_id, "project_code": code}
        except Exception as exc:
            raise _normalize_error(exc)

    def release_alloc(self, alloc_id: int, note: str = "释放") -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    inv.release_alloc(conn, alloc_id, note_append=note or "释放")
            return {"alloc_id": alloc_id, "status": "released"}
        except Exception as exc:
            raise _normalize_error(exc)

    def consume_alloc(self, alloc_id: int, note: str = "已消耗") -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    inv.consume_alloc(conn, alloc_id, note_append=note or "已消耗")
            return {"alloc_id": alloc_id, "status": "consumed"}
        except Exception as exc:
            raise _normalize_error(exc)

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
        except Exception as exc:
            raise _normalize_error(exc)

    def list_resources(self, project_code: str) -> list[dict[str, Any]]:
        with closing(self._conn()) as conn:
            project_id = inv.get_project_id(conn, project_code)
            return [dict(r) for r in list_resources(conn, project_id)]

    def delete_resource(self, project_code: str, resource_type: str, uri: str) -> dict[str, Any]:
        try:
            with closing(self._conn()) as conn:
                with conn:
                    project_id = inv.get_project_id(conn, project_code)
                    deleted = remove_resource(conn, project_id, resource_type, uri)
            return {"deleted": deleted}
        except Exception as exc:
            raise _normalize_error(exc)

    def check_resource(self, project_code: str) -> list[dict[str, Any]]:
        with closing(self._conn()) as conn:
            project_id = inv.get_project_id(conn, project_code)
            return check_resources(conn, project_id)

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
        except Exception as exc:
            raise _normalize_error(exc)
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
        except Exception as exc:
            raise _normalize_error(exc)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
