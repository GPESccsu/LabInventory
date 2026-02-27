"""Tests for the FastAPI endpoints using TestClient."""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi is not installed — skipping API tests")
from fastapi.testclient import TestClient


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
        r = client.get("/api/parts", params={"query": "TEST-001"})
        assert r.status_code == 200
        assert len(r.json()["items"]) >= 1


class TestStockEndpoints:
    def test_stock_in_and_list(self, client: TestClient):
        r = client.post("/api/stock/in", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "qty": 10})
        assert r.status_code == 200
        assert r.json()["ok"]

        r = client.get("/api/stock", params={"query": "TEST-001"})
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        assert items[0]["qty"] == 10

    def test_stock_out(self, client: TestClient):
        client.post("/api/stock/in", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "qty": 20})
        r = client.post("/api/stock/out", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "qty": 5})
        assert r.status_code == 200

    def test_stock_move(self, client: TestClient):
        client.post("/api/stock/in", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "qty": 20})
        r = client.post("/api/stock/move", json={"mpn": "TEST-001", "from_location": "C409-G01-S01-P01", "to_location": "C409-G01-S01-P02", "qty": 5})
        assert r.status_code == 200

    def test_stock_adjust(self, client: TestClient):
        client.post("/api/stock/in", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "qty": 10})
        r = client.post("/api/stock/adjust", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "add_qty": 5, "sub_qty": 0, "note": "test adjust"})
        assert r.status_code == 200

    def test_stock_out_insufficient_returns_400(self, client: TestClient):
        client.post("/api/stock/in", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "qty": 5})
        r = client.post("/api/stock/out", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "qty": 100})
        assert r.status_code == 400


class TestLocationEndpoint:
    def test_list_locations(self, client: TestClient):
        r = client.get("/api/locations")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 2


class TestLedgerEndpoint:
    def test_query_ledger(self, client: TestClient):
        client.post("/api/stock/in", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "qty": 5})
        r = client.get("/api/ledger", params={"mpn": "TEST-001"})
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

    def test_set_bom(self, client: TestClient):
        client.post("/api/projects", json={"code": "PJ-BOM", "name": "BOM测试"})
        client.post("/api/stock/in", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "qty": 100})
        r = client.post("/api/projects/PJ-BOM/bom", json={"items": [{"mpn": "TEST-001", "req_qty": 10}]})
        assert r.status_code == 200
        assert r.json()["ok"]

    def test_project_status(self, client: TestClient):
        client.post("/api/projects", json={"code": "PJ-STA", "name": "状态测试"})
        client.post("/api/stock/in", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "qty": 50})
        client.post("/api/projects/PJ-STA/bom", json={"items": [{"mpn": "TEST-001", "req_qty": 5}]})
        r = client.get("/api/projects/PJ-STA/status")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["req_qty"] == 5


class TestAllocEndpoints:
    def test_reserve_and_release(self, client: TestClient):
        client.post("/api/projects", json={"code": "PJ-AL", "name": "预留API测试"})
        client.post("/api/stock/in", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "qty": 100})
        r = client.post("/api/projects/PJ-AL/reserve", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "qty": 5})
        assert r.status_code == 200
        alloc_id = r.json()["alloc_id"]

        r = client.get("/api/projects/PJ-AL/allocs")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1

        r = client.post(f"/api/allocs/{alloc_id}/release", json={"note": "release test"})
        assert r.status_code == 200
        assert r.json()["status"] == "released"

    def test_reserve_and_consume(self, client: TestClient):
        client.post("/api/projects", json={"code": "PJ-CO", "name": "消耗API测试"})
        client.post("/api/stock/in", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "qty": 100})
        r = client.post("/api/projects/PJ-CO/reserve", json={"mpn": "TEST-001", "location": "C409-G01-S01-P01", "qty": 10})
        alloc_id = r.json()["alloc_id"]

        r = client.post(f"/api/allocs/{alloc_id}/consume", json={"note": "consume test"})
        assert r.status_code == 200
        assert r.json()["status"] == "consumed"

        # stock should be reduced
        r = client.get("/api/stock", params={"query": "TEST-001"})
        total = sum(item["qty"] for item in r.json()["items"])
        assert total == 90
