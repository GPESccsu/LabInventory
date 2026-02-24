"""Tests for the CLI entry point."""
from __future__ import annotations

import subprocess
import sys


def test_cli_help():
    """Verify that `python inv.py --help` works."""
    result = subprocess.run(
        [sys.executable, "inv.py", "--help"],
        capture_output=True,
        text=True,
        cwd="/home/user/LabInventory",
    )
    assert result.returncode == 0
    assert "实验室" in result.stdout or "库存" in result.stdout


def test_cli_subcommand_help():
    """Verify that subcommand help works."""
    for cmd in ["stock-in", "stock-out", "proj-new", "reserve", "ledger"]:
        result = subprocess.run(
            [sys.executable, "inv.py", "--db", "/tmp/__nonexist__.db", cmd, "--help"],
            capture_output=True,
            text=True,
            cwd="/home/user/LabInventory",
        )
        assert result.returncode == 0, f"{cmd} --help failed: {result.stderr}"
