"""Tests for the FastAPI endpoints using TestClient."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.db import connect
from backend.app.inv import init_db


@pytest.fixture
def client(tmp_path: Path):
    """Create a test client with a temporary database."""
    db_path = tmp_path / "test_api.db"
    conn = connect(db_path)
    init_db(conn)
    conn.execute("INSERT OR IGNORE INTO locations (location, note) VALUES ('C409-G01-S01-P01', 'test')")
    conn.execute("INSERT OR IGNORE INTO locations (location, note) VALUES ('C409-G01-S01-P02', 'test2')")
    conn.execute("INSERT INTO parts (mpn, name, category) VALUES ('API-PART-001', 'API测试电阻', '电阻')")
    conn.commit()
    conn.close()

    os.environ["LABINV_DB"] = str(db_path)

    # Re-import to pick up the new DB_PATH
    import importlib
    import backend.app.api as api_mod
    api_mod.DB_PATH = str(db_path)
    api_mod.service = api_mod.InventoryService(str(db_path))

    with TestClient(api_mod.app) as c:
        yield c


class TestHealthEndpoint:
    def test_health(self, client: TestClient):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["parts_count"] >= 1


class TestPartsEndpoint:
    def test_search_parts(self, client: TestClient):
        r = client.get("/api/parts")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1

    def test_search_parts_with_query(self, client: TestClient):
        r = client.get("/api/parts", params={"query": "API-PART"})
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 1


class TestStockEndpoints:
    def test_stock_in_and_list(self, client: TestClient):
        r = client.post("/api/stock/in", json={"mpn": "API-PART-001", "location": "C409-G01-S01-P01", "qty": 10})
        assert r.status_code == 200
        assert r.json()["ok"]

        r = client.get("/api/stock", params={"query": "API-PART"})
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        assert items[0]["qty"] == 10

    def test_stock_out(self, client: TestClient):
        client.post("/api/stock/in", json={"mpn": "API-PART-001", "location": "C409-G01-S01-P01", "qty": 20})
        r = client.post("/api/stock/out", json={"mpn": "API-PART-001", "location": "C409-G01-S01-P01", "qty": 5})
        assert r.status_code == 200

    def test_stock_move(self, client: TestClient):
        client.post("/api/stock/in", json={"mpn": "API-PART-001", "location": "C409-G01-S01-P01", "qty": 20})
        r = client.post("/api/stock/move", json={"mpn": "API-PART-001", "from_location": "C409-G01-S01-P01", "to_location": "C409-G01-S01-P02", "qty": 5})
        assert r.status_code == 200

    def test_stock_adjust(self, client: TestClient):
        client.post("/api/stock/in", json={"mpn": "API-PART-001", "location": "C409-G01-S01-P01", "qty": 10})
        r = client.post("/api/stock/adjust", json={"mpn": "API-PART-001", "location": "C409-G01-S01-P01", "add_qty": 5, "sub_qty": 0, "note": "test adjust"})
        assert r.status_code == 200


class TestLocationEndpoint:
    def test_list_locations(self, client: TestClient):
        r = client.get("/api/locations")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 2


class TestLedgerEndpoint:
    def test_query_ledger(self, client: TestClient):
        client.post("/api/stock/in", json={"mpn": "API-PART-001", "location": "C409-G01-S01-P01", "qty": 5})
        r = client.get("/api/ledger", params={"mpn": "API-PART-001"})
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1


class TestProjectEndpoints:
    def test_create_project(self, client: TestClient):
        r = client.post("/api/projects", json={"code": "PJ-API", "name": "API测试项目"})
        assert r.status_code == 200
        assert r.json()["code"] == "PJ-API"

    def test_list_projects(self, client: TestClient):
        client.post("/api/projects", json={"code": "PJ-LIST", "name": "列表测试"})
        r = client.get("/api/projects")
        assert r.status_code == 200
        codes = [p["code"] for p in r.json()["items"]]
        assert "PJ-LIST" in codes

    def test_project_detail(self, client: TestClient):
        client.post("/api/projects", json={"code": "PJ-DETAIL", "name": "详情测试"})
        r = client.get("/api/projects/PJ-DETAIL")
        assert r.status_code == 200
        assert r.json()["name"] == "详情测试"

    def test_project_not_found(self, client: TestClient):
        r = client.get("/api/projects/NOPE")
        assert r.status_code == 404
