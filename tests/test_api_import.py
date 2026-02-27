"""API import smoke tests — verify that the FastAPI module and all schemas load correctly."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


class TestAPIImportSmoke:
    """The api module must be importable when fastapi is available."""

    def test_api_module_imports(self):
        """backend.app.api must import without NameError or missing schema references."""
        fastapi = pytest.importorskip("fastapi", reason="fastapi not installed")
        import backend.app.api as api_mod

        assert hasattr(api_mod, "app"), "FastAPI app instance missing"

    def test_all_routes_have_response_model(self):
        """Every route that declares a response_model must reference a real Pydantic class."""
        fastapi = pytest.importorskip("fastapi", reason="fastapi not installed")
        import backend.app.api as api_mod

        for route in api_mod.app.routes:
            if not hasattr(route, "response_model"):
                continue
            model = route.response_model
            if model is not None:
                assert hasattr(model, "model_fields"), (
                    f"Route {route.path} response_model {model} is not a Pydantic model"
                )

    def test_schemas_complete(self):
        """All schema classes referenced in api.py must exist in schemas module."""
        import backend.app.schemas as schemas

        required = [
            "HealthResponse",
            "PartListResponse",
            "StockListResponse",
            "StockInRequest",
            "StockOutRequest",
            "StockMoveRequest",
            "StockAdjustRequest",
            "LocationListResponse",
            "LedgerResponse",
            "GenericResult",
            "ProjectResponse",
            "ProjectListResponse",
            "ProjectStatusResponse",
            "ProjectAllocResponse",
            "BomBatchRequest",
            "ReserveRequest",
            "ReserveResponse",
            "AllocActionRequest",
            "AllocActionResponse",
            "ResourceUpsertRequest",
            "ResourceDeleteRequest",
            "ResourceListResponse",
            "ResourceCheckResponse",
            "ImportResponse",
            "ProjectUpsertRequest",
        ]
        for name in required:
            assert hasattr(schemas, name), f"schemas.py is missing model: {name}"


class TestInitDbIdempotent:
    """init_db must be safe to call multiple times on the same database."""

    def test_init_db_twice_no_error(self, tmp_path: Path):
        from backend.app.db import connect, init_db

        db = tmp_path / "idempotent.db"
        conn = connect(db)
        init_db(conn)
        # Second call must not raise
        init_db(conn)
        conn.close()

    def test_init_db_creates_core_tables(self, tmp_path: Path):
        from backend.app.db import connect, init_db

        db = tmp_path / "tables.db"
        conn = connect(db)
        init_db(conn)

        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {"parts", "stock", "locations", "projects", "project_bom",
                    "project_alloc", "inv_doc", "inv_line", "project_resources"}
        missing = expected - tables
        assert not missing, f"Missing tables after init_db: {missing}"
        conn.close()

    def test_init_db_preserves_data_on_reinit(self, tmp_path: Path):
        """Re-running init_db must not drop existing data."""
        from backend.app.db import connect, init_db

        db = tmp_path / "preserve.db"
        conn = connect(db)
        init_db(conn)
        conn.execute(
            "INSERT INTO parts (mpn, name, category) VALUES ('KEEP-001', 'keep part', 'test')"
        )
        conn.commit()

        # Re-init should not destroy the row
        init_db(conn)
        row = conn.execute("SELECT mpn FROM parts WHERE mpn='KEEP-001'").fetchone()
        assert row is not None, "init_db destroyed existing data"
        assert row["mpn"] == "KEEP-001"
        conn.close()
