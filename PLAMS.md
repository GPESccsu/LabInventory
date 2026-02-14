# Plan: Electronics Inventory DB (Ledger + Optional Project)

## 0. Objective
Enhance the existing SQLite inventory system to support:
- Auditable stock operations (IN/OUT/MOVE/ADJUST) via ledger tables.
- Operations optionally linked to projects (project_id nullable).
- Preserve existing schema + triggers + views + CLI commands.

## 1. Current state (confirmed in inv.py)
- Balance tables: stock(part_id, location, qty) is the source of truth.
- Project reservation: project_alloc with triggers preventing over-reserve.
- Consume flow: consume_alloc() deducts stock and marks alloc consumed.
- CLI supports stock-in, reserve, consume, project status, LCSC import, etc.
- Missing:
  - General stock-out (non-reservation) command
  - Move between locations
  - Adjust stock with audit trail
  - Unified ledger for all stock changes

## 2. Target design (additive)
### 2.1 New tables
A) inv_doc (document header)
- id INTEGER PK
- doc_type TEXT CHECK IN ('IN','OUT','MOVE','ADJUST','CONSUME','RESERVE','RELEASE')
- project_id INTEGER NULL  (optional)
- from_location TEXT NULL
- to_location TEXT NULL
- ref TEXT, operator TEXT, note TEXT
- created_at TEXT DEFAULT datetime('now','localtime')
- Optional link: alloc_id INTEGER NULL (for reserve/consume linkage)

B) inv_line (document lines)
- id INTEGER PK
- doc_id INTEGER NOT NULL FK inv_doc(id) ON DELETE CASCADE
- part_id INTEGER NOT NULL FK parts(id)
- qty INTEGER NOT NULL CHECK(qty>0)
- unit_cost REAL NULL
- note TEXT NULL

Indexes: by (project_id), (created_at), (part_id)

### 2.2 Compatibility
- Do NOT modify existing tables/columns used by current code paths.
- Keep v_project_material_status and triggers intact (still based on stock + project_alloc).
- Ledger is used for audit/reporting; stock remains the balance table.

## 3. Business rules
- IN: increase stock at to_location; record inv_doc+inv_line
- OUT: decrease stock at from_location; reject if insufficient; record inv_doc+inv_line
- MOVE: decrease from_location and increase to_location; reject if insufficient
- ADJUST:
  - mode add/sub, requires note/ref
  - if sub: reject if insufficient
- Existing RESERVE/RELEASE/CONSUME flows:
  - Keep project_alloc triggers.
  - Additionally write ledger documents:
    - RESERVE: inv_doc(doc_type='RESERVE', project_id, to_location=location, alloc_id)
    - RELEASE: inv_doc(doc_type='RELEASE', alloc_id)
    - CONSUME: inv_doc(doc_type='CONSUME', project_id, from_location=location, alloc_id) + inv_line(qty=alloc_qty)
  - consume_alloc() must become the single source that both updates stock and writes ledger, within one transaction.

## 4. CLI additions (must be backward compatible)
Add new subcommands without breaking existing ones:
- stock-out:  inv stock-out --mpn MPN --loc LOC --qty N [--proj CODE] [--ref ...] [--note ...] [--operator ...]
- stock-move: inv stock-move --mpn MPN --from LOC --to LOC --qty N [--note ...]
- stock-adjust:
  - inv stock-adjust --mpn MPN --loc LOC --add N --note REASON
  - inv stock-adjust --mpn MPN --loc LOC --sub N --note REASON
- ledger query:
  - inv ledger [--proj CODE] [--mpn MPN] [--since YYYY-MM-DD]

Existing commands unchanged:
- stock-in, reserve, release, consume, proj-status, proj-alloc, lcsc, proj-forms, init-locations

## 5. Implementation steps (small chunks)
Step 1: Schema export + inspection
- Export docs/schema_before.sql
- Confirm current DDL and how init_db() applies it.

Step 2: Add ledger tables + indexes to DDL
- Extend the DDL string in inv.py (idempotent CREATE TABLE IF NOT EXISTS).
- Add minimal views if helpful (e.g., v_ledger_join with mpn/project_code).

Step 3: Implement stock mutation API (single module section)
- Functions:
  - stock_in(mpn, loc, qty, project_code_optional, ...)
  - stock_out(...)
  - stock_move(...)
  - stock_adjust(...)
  - write_ledger(doc_type,..., lines=[(part_id, qty, note)])
- Ensure all operations are transactional and reject negative stock.

Step 4: Wire new CLI commands to these functions
- Add argparse subparsers and handlers.

Step 5: Integrate ledger into existing flows
- Modify add_stock() to also write ledger doc_type='IN' (optional: only when called from CLI; keep behavior stable).
- Modify consume_alloc() to write ledger doc_type='CONSUME' with project_id (lookup from project_alloc).
- Modify reserve/release to optionally write ledger docs (recommended).

Step 6: Smoke test script
- Add scripts/smoke_test_ledger.py (or .sh) creating a temp db:
  - init-locations (or insert a location)
  - insert a part
  - stock-in 100
  - stock-out 30 (project optional)
  - stock-move 20
  - stock-adjust sub 10
  - reserve 10, consume
  - Assert final stock quantities and ledger row counts.

Step 7: Export docs/schema_after.sql and update README
- Document new commands + examples.
- Explain optional project usage.

## 6. Definition of Done
- Old commands still work (stock-in/reserve/consume/proj-status/proj-forms).
- New commands work with correct stock updates.
- Negative stock is rejected for OUT/MOVE/ADJUST-sub/CONSUME.
- Every stock-changing operation writes ledger records.
- docs/schema_before.sql and docs/schema_after.sql exist.
- Smoke tests pass.

## 7. Verification commands (Codex must run)
- python inv.py --db <db> init-locations ...
- python inv.py --db <db> stock-in ...
- python inv.py --db <db> stock-out ...
- python inv.py --db <db> stock-move ...
- python inv.py --db <db> stock-adjust ...
- python inv.py --db <db> reserve/consume ...
- sqlite3 <db> "select count(*) from inv_doc;"
