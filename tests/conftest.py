"""Shared test fixtures for all test modules."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core import InventoryService
from backend.app.db import connect, init_db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database with schema initialized and seed data."""
    p = tmp_path / "test.db"
    conn = connect(p)
    init_db(conn)
    conn.execute("INSERT OR IGNORE INTO locations (location, note) VALUES ('C409-G01-S01-P01', 'test loc 1')")
    conn.execute("INSERT OR IGNORE INTO locations (location, note) VALUES ('C409-G01-S01-P02', 'test loc 2')")
    conn.execute(
        "INSERT INTO parts (mpn, name, category, package, params) VALUES ('TEST-001', '测试电阻', '电阻', '0402', '10kΩ')"
    )
    conn.commit()
    conn.close()
    return p


@pytest.fixture
def svc(db_path: Path) -> InventoryService:
    """Create an InventoryService backed by the temporary database."""
    return InventoryService(db_path)


@pytest.fixture
def client(db_path: Path):
    """Create a FastAPI TestClient backed by the temporary database."""
    os.environ["LABINV_DB"] = str(db_path)

    import backend.app.api as api_mod
    api_mod.DB_PATH = str(db_path)
    api_mod.service = InventoryService(str(db_path))

    with TestClient(api_mod.app) as c:
        yield c
