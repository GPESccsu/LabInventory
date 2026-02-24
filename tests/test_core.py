"""Tests for the core inventory service using an in-memory SQLite database."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.app.core import InventoryError, InventoryService, NotFoundError
from backend.app.db import connect
from backend.app.inv import init_db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database with schema initialized."""
    p = tmp_path / "test.db"
    conn = connect(p)
    init_db(conn)
    # seed some locations
    conn.execute("INSERT OR IGNORE INTO locations (location, note) VALUES ('C409-G01-S01-P01', 'test loc 1')")
    conn.execute("INSERT OR IGNORE INTO locations (location, note) VALUES ('C409-G01-S01-P02', 'test loc 2')")
    # seed a part
    conn.execute(
        "INSERT INTO parts (mpn, name, category, package, params) VALUES ('TEST-001', '测试电阻', '电阻', '0402', '10kΩ')"
    )
    conn.commit()
    conn.close()
    return p


@pytest.fixture
def svc(db_path: Path) -> InventoryService:
    return InventoryService(db_path)


class TestHealth:
    def test_health_returns_ok(self, svc: InventoryService):
        result = svc.health()
        assert result["status"] == "ok"
        assert result["parts_count"] >= 1
        assert "db_path" in result


class TestParts:
    def test_search_parts_all(self, svc: InventoryService):
        parts = svc.search_parts()
        assert len(parts) >= 1
        assert parts[0]["mpn"] == "TEST-001"

    def test_search_parts_by_query(self, svc: InventoryService):
        parts = svc.search_parts("TEST-001")
        assert len(parts) == 1

    def test_search_parts_no_match(self, svc: InventoryService):
        parts = svc.search_parts("NONEXISTENT-XYZ")
        assert len(parts) == 0


class TestProjects:
    def test_create_and_get_project(self, svc: InventoryService):
        result = svc.upsert_project("PJ-TEST", "测试项目", "tester", "unit test")
        assert result["code"] == "PJ-TEST"
        assert result["name"] == "测试项目"

        proj = svc.get_project("PJ-TEST")
        assert proj["code"] == "PJ-TEST"

    def test_list_projects(self, svc: InventoryService):
        svc.upsert_project("PJ-A", "项目A")
        svc.upsert_project("PJ-B", "项目B")
        projects = svc.list_projects()
        codes = [p["code"] for p in projects]
        assert "PJ-A" in codes
        assert "PJ-B" in codes

    def test_list_projects_with_query(self, svc: InventoryService):
        svc.upsert_project("PJ-FIND", "搜索测试")
        projects = svc.list_projects("FIND")
        assert len(projects) >= 1

    def test_get_nonexistent_project(self, svc: InventoryService):
        with pytest.raises(NotFoundError):
            svc.get_project("NOPE")


class TestStock:
    def test_stock_in_and_list(self, svc: InventoryService):
        svc.stock_in("TEST-001", "C409-G01-S01-P01", 10, condition="new", note="test in")
        rows = svc.list_stock("TEST-001")
        assert len(rows) == 1
        assert rows[0]["qty"] == 10
        assert rows[0]["mpn"] == "TEST-001"

    def test_stock_out(self, svc: InventoryService):
        svc.stock_in("TEST-001", "C409-G01-S01-P01", 20)
        svc.stock_out("TEST-001", "C409-G01-S01-P01", 5)
        rows = svc.list_stock("TEST-001")
        assert rows[0]["qty"] == 15

    def test_stock_out_insufficient(self, svc: InventoryService):
        svc.stock_in("TEST-001", "C409-G01-S01-P01", 5)
        with pytest.raises(RuntimeError, match="库存不足"):
            svc.stock_out("TEST-001", "C409-G01-S01-P01", 100)

    def test_stock_move(self, svc: InventoryService):
        svc.stock_in("TEST-001", "C409-G01-S01-P01", 10)
        svc.stock_move("TEST-001", "C409-G01-S01-P01", "C409-G01-S01-P02", 3)
        rows = svc.list_stock("TEST-001")
        by_loc = {r["location"]: r["qty"] for r in rows}
        assert by_loc["C409-G01-S01-P01"] == 7
        assert by_loc["C409-G01-S01-P02"] == 3

    def test_stock_adjust_add(self, svc: InventoryService):
        svc.stock_in("TEST-001", "C409-G01-S01-P01", 10)
        svc.stock_adjust("TEST-001", "C409-G01-S01-P01", add_qty=5, note="盘点补差")
        rows = svc.list_stock("TEST-001")
        assert rows[0]["qty"] == 15

    def test_stock_adjust_sub(self, svc: InventoryService):
        svc.stock_in("TEST-001", "C409-G01-S01-P01", 10)
        svc.stock_adjust("TEST-001", "C409-G01-S01-P01", sub_qty=3, note="盘点减少")
        rows = svc.list_stock("TEST-001")
        assert rows[0]["qty"] == 7

    def test_list_stock_by_location(self, svc: InventoryService):
        svc.stock_in("TEST-001", "C409-G01-S01-P01", 10)
        rows = svc.list_stock(location="P01")
        assert len(rows) >= 1
        rows2 = svc.list_stock(location="P99")
        assert len(rows2) == 0


class TestLocations:
    def test_list_locations(self, svc: InventoryService):
        locs = svc.list_locations()
        assert len(locs) >= 2
        loc_names = [loc["location"] for loc in locs]
        assert "C409-G01-S01-P01" in loc_names


class TestLedger:
    def test_ledger_records_stock_in(self, svc: InventoryService):
        svc.stock_in("TEST-001", "C409-G01-S01-P01", 10, note="ledger test")
        rows = svc.query_ledger(mpn="TEST-001")
        assert len(rows) >= 1
        assert rows[0]["doc_type"] == "IN"

    def test_ledger_filter_by_date(self, svc: InventoryService):
        svc.stock_in("TEST-001", "C409-G01-S01-P01", 5)
        rows = svc.query_ledger(since="2020-01-01")
        assert len(rows) >= 1
        # future date should return nothing
        rows2 = svc.query_ledger(since="2099-01-01")
        assert len(rows2) == 0


class TestProjectBomAndAlloc:
    def test_bom_set_and_status(self, svc: InventoryService):
        svc.upsert_project("PJ-BOM", "BOM测试")
        svc.stock_in("TEST-001", "C409-G01-S01-P01", 100)
        svc.set_project_bom("PJ-BOM", [{"mpn": "TEST-001", "req_qty": 10}])
        status = svc.get_project_status("PJ-BOM")
        assert len(status) == 1
        assert status[0]["req_qty"] == 10

    def test_reserve_and_release(self, svc: InventoryService):
        svc.upsert_project("PJ-ALLOC", "预留测试")
        svc.stock_in("TEST-001", "C409-G01-S01-P01", 100)
        result = svc.reserve("PJ-ALLOC", "TEST-001", "C409-G01-S01-P01", 5, "reserve test")
        alloc_id = result["alloc_id"]
        assert alloc_id > 0

        allocs = svc.get_project_allocs("PJ-ALLOC")
        assert len(allocs) == 1
        assert allocs[0]["status"] == "reserved"

        svc.release_alloc(alloc_id, "release test")
        allocs = svc.get_project_allocs("PJ-ALLOC")
        assert allocs[0]["status"] == "released"

    def test_reserve_and_consume(self, svc: InventoryService):
        svc.upsert_project("PJ-CONS", "消耗测试")
        svc.stock_in("TEST-001", "C409-G01-S01-P01", 100)
        result = svc.reserve("PJ-CONS", "TEST-001", "C409-G01-S01-P01", 5)
        alloc_id = result["alloc_id"]

        svc.consume_alloc(alloc_id)
        allocs = svc.get_project_allocs("PJ-CONS")
        assert allocs[0]["status"] == "consumed"

        # stock should be reduced
        stock = svc.list_stock("TEST-001")
        total = sum(r["qty"] for r in stock)
        assert total == 95
