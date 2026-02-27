"""Transaction integrity tests — CHECK constraints and triggers at the DB level."""
from __future__ import annotations

import sqlite3

import pytest

from backend.app.db import connect, init_db


@pytest.fixture
def conn(db_path):
    """Return an open connection to the temporary test database."""
    c = connect(db_path)
    yield c
    c.close()


def _seed_inv_doc(conn: sqlite3.Connection, doc_type: str = "ADJUST") -> int:
    """Insert a valid inv_doc row and return its id."""
    cur = conn.execute(
        "INSERT INTO inv_doc (doc_type) VALUES (?)", (doc_type,)
    )
    conn.commit()
    return cur.lastrowid


def _get_part_id(conn: sqlite3.Connection) -> int:
    """Return the id of the seed part TEST-001."""
    row = conn.execute("SELECT id FROM parts WHERE mpn = 'TEST-001'").fetchone()
    return row["id"]


# ---------------------------------------------------------------------------
# INSERT tests — CHECK constraints reject invalid data on INSERT
# ---------------------------------------------------------------------------


class TestInsertConstraints:
    """Prove that CHECK constraints block illegal INSERTs."""

    def test_inv_line_qty_zero_rejected(self, conn):
        """INSERT into inv_line with qty=0 must be rejected (CHECK qty > 0)."""
        doc_id = _seed_inv_doc(conn, "ADJUST")
        part_id = _get_part_id(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO inv_line (doc_id, part_id, qty) VALUES (?, ?, 0)",
                (doc_id, part_id),
            )

    def test_inv_line_qty_negative_rejected(self, conn):
        """INSERT into inv_line with qty<0 must be rejected (CHECK qty > 0)."""
        doc_id = _seed_inv_doc(conn, "ADJUST")
        part_id = _get_part_id(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO inv_line (doc_id, part_id, qty) VALUES (?, ?, -5)",
                (doc_id, part_id),
            )

    def test_inv_doc_invalid_doc_type_rejected(self, conn):
        """INSERT into inv_doc with an invalid doc_type must be rejected."""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO inv_doc (doc_type) VALUES ('INVALID')"
            )

    def test_inventory_txn_invalid_type_rejected(self, conn):
        """INSERT into inventory_txn with an invalid txn_type must be rejected."""
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO inventory_txn (txn_type) VALUES ('INVALID')"
            )


# ---------------------------------------------------------------------------
# UPDATE tests — CHECK constraints reject illegal UPDATEs
# ---------------------------------------------------------------------------


class TestUpdateConstraints:
    """Prove that CHECK constraints block illegal UPDATEs on existing rows."""

    def test_update_inv_doc_to_invalid_type_rejected(self, conn):
        """UPDATE inv_doc.doc_type to an illegal symbol must be rejected."""
        doc_id = _seed_inv_doc(conn, "ADJUST")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE inv_doc SET doc_type = 'INVALID' WHERE id = ?",
                (doc_id,),
            )

    def test_update_inv_line_qty_to_zero_rejected(self, conn):
        """UPDATE inv_line.qty to 0 must be rejected (CHECK qty > 0)."""
        doc_id = _seed_inv_doc(conn, "ADJUST")
        part_id = _get_part_id(conn)
        conn.execute(
            "INSERT INTO inv_line (doc_id, part_id, qty) VALUES (?, ?, 10)",
            (doc_id, part_id),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE inv_line SET qty = 0 WHERE doc_id = ? AND part_id = ?",
                (doc_id, part_id),
            )

    def test_update_inventory_txn_to_invalid_type_rejected(self, conn):
        """UPDATE inventory_txn.txn_type to an illegal value must be rejected."""
        cur = conn.execute(
            "INSERT INTO inventory_txn (txn_type) VALUES ('ADJUST')"
        )
        conn.commit()
        txn_id = cur.lastrowid
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE inventory_txn SET txn_type = 'BOGUS' WHERE id = ?",
                (txn_id,),
            )
