"""CLI smoke tests — verify that inv.py can be imported and help works."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INV_PY = ROOT / "inv.py"


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Create a minimal SQLite database for CLI testing."""
    from backend.app.db import connect, init_db

    p = tmp_path / "smoke.db"
    conn = connect(p)
    init_db(conn)
    conn.close()
    return p


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(INV_PY), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestCLIHelp:
    """--help for the main command and key subcommands should exit 0."""

    def test_main_help(self, tmp_db: Path) -> None:
        r = _run_cli("--db", str(tmp_db), "--help")
        assert r.returncode == 0
        assert "实验室元器件" in r.stdout

    def test_stock_in_help(self, tmp_db: Path) -> None:
        r = _run_cli("--db", str(tmp_db), "stock-in", "--help")
        assert r.returncode == 0
        assert "--mpn" in r.stdout

    def test_schema_export_help(self, tmp_db: Path) -> None:
        r = _run_cli("--db", str(tmp_db), "schema-export", "--help")
        assert r.returncode == 0
        assert "--format" in r.stdout

    def test_lcsc_help(self, tmp_db: Path) -> None:
        r = _run_cli("--db", str(tmp_db), "lcsc", "--help")
        assert r.returncode == 0
        assert "--url" in r.stdout

    def test_ledger_help(self, tmp_db: Path) -> None:
        r = _run_cli("--db", str(tmp_db), "ledger", "--help")
        assert r.returncode == 0

    def test_proj_status_help(self, tmp_db: Path) -> None:
        r = _run_cli("--db", str(tmp_db), "proj-status", "--help")
        assert r.returncode == 0


class TestCLIImportable:
    """Module-level import must not fail (no eager optional-dep imports)."""

    def test_import_inv(self) -> None:
        r = subprocess.run(
            [sys.executable, "-c", "import backend.app.inv"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert r.returncode == 0, f"Import failed:\n{r.stderr}"
