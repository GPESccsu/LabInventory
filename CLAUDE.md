# CLAUDE.md — LabInventory

AI assistant guide for the LabInventory codebase. Read this before making any changes.

## Project Overview

LabInventory is an **electronic component inventory management system** for a lab environment (room C409). It tracks parts, stock levels, project BOM allocations, and stock transactions. The system has three interfaces sharing one SQLite database:

1. **CLI** (`python inv.py --db <path> <subcommand>`) — primary management interface
2. **FastAPI** backend (`backend/app/api.py`) — HTTP REST API
3. **Streamlit** frontend (`frontend/streamlit_app.py`) — Chinese web UI

The UI language is Chinese (中文) throughout: error messages, CLI help text, and the web UI.

---

## Repository Layout

```
LabInventory/
├── backend/
│   └── app/
│       ├── inv.py              # Core business logic + CLI main()
│       ├── db.py               # SQLite connect() + init_db()
│       ├── core.py             # InventoryService class (used by API)
│       ├── schemas.py          # Pydantic request/response models
│       ├── api.py              # FastAPI app + all route handlers
│       └── project_resources.py # Project resource CRUD + XLSX import
├── frontend/
│   └── streamlit_app.py        # Streamlit web UI (calls API via HTTP)
├── app/                        # Compatibility shim → backend.app
│   ├── __init__.py
│   ├── api.py                  # re-exports backend.app.api
│   ├── core.py                 # re-exports backend.app.core
│   ├── db.py                   # re-exports backend.app.db
│   ├── inv.py                  # re-exports backend.app.inv
│   ├── project_resources.py    # re-exports backend.app.project_resources
│   └── schemas.py              # re-exports backend.app.schemas
├── ui/
│   └── streamlit_app.py        # Compatibility shim → frontend.streamlit_app
├── inv.py                      # CLI entry point shim (calls app.inv.main)
├── scripts/
│   ├── import_bom.py           # BOM import utility
│   ├── lcsc_to_db.py           # LCSC data import utility
│   ├── export_bom_parts_data.py
│   ├── smoke_test_ledger.py    # Ledger smoke test
│   └── project_bom_allocation_example.py
├── data/                       # JSON exports, SQL schema snapshots, docs
├── schema/                     # DB schema SQL files
├── docs/                       # Additional documentation
├── datasheets/                 # Downloaded component datasheets (gitignored)
├── lab_inventory.db            # SQLite database (main data store)
├── pyproject.toml              # Poetry project config
├── AGENTS.md                   # Agent task instructions (Chinese)
├── PLAN.md                     # Implementation plan log
└── README.md                   # User-facing setup guide (Chinese)
```

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Language | Python ≥3.11, <3.14 |
| Package manager | Poetry |
| Database | SQLite (WAL mode) |
| HTTP API | FastAPI + Uvicorn |
| Web UI | Streamlit |
| Data validation | Pydantic v2 |
| XLSX handling | openpyxl, pandas |
| Web scraping | requests, beautifulsoup4 |

---

## Development Setup

```bash
# Install dependencies
poetry install

# Start FastAPI backend (port 8000)
poetry run uvicorn backend.app.api:app --host 0.0.0.0 --port 8000

# Start Streamlit frontend (separate terminal)
poetry run streamlit run frontend/streamlit_app.py

# Run CLI
python inv.py --db ./lab_inventory.db --help
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `LABINV_DB` | `./lab_inventory.db` | Database file path (used by FastAPI) |
| `LABINV_API_BASE` | `http://127.0.0.1:8000` | API base URL (used by Streamlit) |

---

## Database Schema

The database is initialized idempotently via `init_db()` in `backend/app/inv.py`. All DDL uses `IF NOT EXISTS`.

### Core Tables

| Table | Key Columns | Purpose |
|-------|-------------|---------|
| `parts` | `id`, `mpn` (unique), `name`, `category`, `package`, `params`, `url`, `datasheet` | Component master data |
| `stock` | `id`, `part_id`, `location`, `qty`, `condition` | Physical stock per location |
| `locations` | `location` (PK), `note` | Valid storage locations |
| `projects` | `id`, `code` (unique), `name`, `owner`, `status` | Project registry |
| `project_bom` | `project_id`, `part_id`, `req_qty`, `priority` | Per-project BOM |
| `project_alloc` | `id`, `project_id`, `part_id`, `location`, `alloc_qty`, `status` | Part reservations |
| `inv_doc` | `id`, `doc_type`, `project_id`, `from_location`, `to_location`, `ref`, `operator` | Transaction documents |
| `inv_line` | `id`, `doc_id`, `part_id`, `qty`, `unit_cost` | Transaction line items |
| `project_resources` | `id`, `project_id`, `type`, `name`, `uri`, `is_dir`, `tags` | Project file/URL resources |

### Views

| View | Purpose |
|------|---------|
| `v_project_material_status` | BOM + stock + reservation status per project |

### Triggers

- `trg_alloc_location_check` / `_u` — validates location exists in `locations` table on INSERT/UPDATE
- `trg_alloc_no_overreserve_ins` / `_upd` — **hard blocks** over-reservation both globally and per-location

### SQLite Connection Settings

All connections in `backend/app/db.py` use:
```python
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA synchronous=NORMAL;")
conn.execute("PRAGMA busy_timeout=30000;")
conn.execute("PRAGMA foreign_keys=ON;")
```

---

## CLI Reference (`python inv.py --db <path> <subcommand>`)

### Query & Search (查询)

```bash
parts      [--query <KEYWORD>] [--limit 200]           # 搜索/列出物料（按MPN/名称/分类/封装）
stock-list [--query <KEYWORD>] [--loc <LOC>] [--limit 500]  # 查看库存（可按物料/库位过滤）
locations                                               # 列出所有库位
project list [--query <KEYWORD>]                        # 搜索/列出项目（按code/名称/负责人）
stats                                                   # 系统统计信息（物料/库存/项目/库位等）
```

### Stock Management

```bash
stock-in  --mpn <MPN> --loc <LOC> --qty <N> [--condition new] [--note ""]
stock-out --mpn <MPN> --loc <LOC> --qty <N> [--proj <CODE>] [--ref ""] [--note ""] [--operator ""]
stock-move --mpn <MPN> --from <LOC> --to <LOC> --qty <N> [--note ""] [--operator ""]
stock-adjust --mpn <MPN> --loc <LOC> (--add N | --sub N) --note <reason> [--ref ""] [--operator ""]
```

### Project Management

```bash
proj-new  --code <CODE> --name <NAME> [--owner ""] [--note ""]
bom-set   --proj <CODE> --mpn <MPN> --req <N> [--priority 2] [--note ""]
reserve   --proj <CODE> --mpn <MPN> --loc <LOC> --qty <N> [--note ""]
release   --id <ALLOC_ID> [--note "释放"]
consume   --id <ALLOC_ID> [--note "已消耗"]
proj-status --proj <CODE>
proj-alloc  --proj <CODE>

# Newer hierarchical form (equivalent)
project add --code <CODE> --name <NAME> [--owner ""] [--note ""]
project overview [--code <CODE>]
project list [--query <KEYWORD>]
```

### Project Resources

```bash
project resource add    --code <CODE> --type <TYPE> --name <NAME> --uri <URI> [--is-dir 1] [--tags ""] [--note ""] [--no-check]
project resource ls     --code <CODE>
project resource rm     --code <CODE> --type <TYPE> --uri <URI>
project resource check  --code <CODE>
project resource import-xlsx --xlsx <PATH> [--sheet project_resources] [--header-row 1] [--auto-create-project] [--no-check]
```

### Utilities

```bash
init-locations --room C409 [--g01-shelves 3] [--g02-shelves 1] [--positions 10] [--overwrite-note]
lcsc  --url <LCSC_URL> [--datasheets-dir <DIR>]
ledger [--proj <CODE>] [--mpn <MPN>] [--since YYYY-MM-DD]
schema-export [--format sql|md] [--out <PATH>]
txn-export-xlsx --out <PATH>
txn-import-xlsx --xlsx <PATH> [--mode auto|transactions|stock-io] [--partial] [--error-out <PATH>]
proj-forms --proj <CODE> [--outbound-csv <PATH>] [--inbound-csv <PATH>] [--lcsc-file <PATH>] [--apply-inbound] [--inbound-loc <LOC>]
stats
```

---

## FastAPI Endpoints (`backend/app/api.py`)

Base URL: `http://0.0.0.0:8000`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | System health check |
| GET | `/api/parts` | Search parts (optional `?query=`) |
| GET | `/api/stock` | List stock (optional `?query=`, `?location=`) |
| GET | `/api/locations` | List all storage locations |
| GET | `/api/ledger` | Query transaction ledger (`?project=`, `?mpn=`, `?since=`) |
| POST | `/api/lcsc/import` | Import part from LCSC URL |
| POST | `/api/stock/in` | Stock in (add qty) |
| POST | `/api/stock/out` | Stock out (deduct qty) |
| POST | `/api/stock/move` | Move stock between locations |
| POST | `/api/stock/adjust` | Adjust stock quantity |
| POST | `/api/projects` | Create or update a project |
| GET | `/api/projects` | List projects (optional `?query=`) |
| GET | `/api/projects/{code}` | Get project detail |
| GET | `/api/projects/{code}/status` | Project BOM+stock+alloc status |
| GET | `/api/projects/{code}/allocs` | Project allocation details |
| POST | `/api/projects/{code}/bom` | Set project BOM (batch) |
| POST | `/api/projects/{code}/reserve` | Reserve parts for a project |
| POST | `/api/allocs/{id}/release` | Release an allocation |
| POST | `/api/allocs/{id}/consume` | Consume an allocation |
| POST | `/api/projects/{code}/resources` | Add/update a project resource |
| GET | `/api/projects/{code}/resources` | List project resources |
| DELETE | `/api/projects/{code}/resources` | Delete a project resource |
| POST | `/api/projects/{code}/resources/check` | Check resource URI validity |
| POST | `/api/projects/resources/import-xlsx` | Batch import resources from XLSX |
| POST | `/api/txns/import-xlsx` | Batch import transactions from XLSX |

### Error HTTP Status Codes

- `404` — `NotFoundError` (project/part not found)
- `409` — `DatabaseLockedError` (SQLite busy)
- `400` — all other `InventoryError` variants

---

## Streamlit Frontend Tabs (`frontend/streamlit_app.py`)

The Streamlit web UI provides 7 tabs covering all system functionality:

| Tab | Features |
|-----|----------|
| 系统概览 | System health metrics (parts/stock/projects count) |
| 物料管理 | Search/list parts; LCSC import (立创商城导入) |
| 库存管理 | Stock query; stock-in/out/move/adjust; locations list |
| 项目管理 | Project CRUD; BOM status; reserve/release/consume |
| 项目资源 | Resource add/list/delete/check per project |
| 交易流水 | Ledger query (by project, MPN, date) |
| 导入导出 | XLSX transaction import; XLSX resource import |

---

## Code Architecture

### Layering

```
CLI (inv.py main)          Streamlit UI (HTTP client)
        │                           │
        ▼                           ▼ (HTTP)
backend/app/inv.py         FastAPI (backend/app/api.py)
  business functions               │
        │                          ▼
        └──────────── InventoryService (backend/app/core.py)
                               │
                     backend/app/inv.py (shared functions)
                               │
                      backend/app/db.py (connect / init_db)
                               │
                           SQLite DB
```

### Key Classes and Patterns

**`InventoryService`** (`backend/app/core.py`):
- Wraps all business operations for use by the API
- Opens and closes connections per-call via `contextlib.closing`
- Normalizes SQLite errors with `_normalize_error()`

**`connect()`** (`backend/app/db.py`):
- Always sets WAL, synchronous=NORMAL, busy_timeout=30000, foreign_keys=ON
- Sets `row_factory = sqlite3.Row` so rows behave like dicts

**`init_db()`** (`backend/app/inv.py`):
- Executes the full `DDL` string — idempotent via `IF NOT EXISTS`
- Called on every connection open; safe to call repeatedly

**Error hierarchy** (`backend/app/core.py`):
```python
InventoryError(RuntimeError)
├── DatabaseLockedError   # "database is locked"
└── NotFoundError         # resource doesn't exist
```

---

## Critical Compatibility Rules

These rules come from `AGENTS.md` and must be strictly followed:

1. **Never remove or rename** existing CLI subcommands, arguments, tables, views, or triggers.
2. **All DDL must be idempotent** — use `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `CREATE TRIGGER IF NOT EXISTS`, `CREATE VIEW IF NOT EXISTS`. The only exception is replacing DROP+CREATE for triggers that need updating (use `DROP TRIGGER IF EXISTS` then `CREATE TRIGGER`).
3. **`python inv.py --help` must always work** — never break the CLI entry point.
4. **The `--db` argument is required** for all CLI invocations; the API uses the `LABINV_DB` env var.
5. **Windows path compatibility**: `resolve_input_path()` and `resolve_output_path()` in `inv.py` handle Windows-style paths (e.g., `G:\LabInventory\...`). Do not break this logic.
6. **No over-reservation**: The DB triggers `trg_alloc_no_overreserve_ins/upd` are the hard enforcement layer — do not weaken them.
7. **Compatibility shims** at `app/`, `ui/`, and `inv.py` must continue to re-export from the real implementations in `backend/` and `frontend/`.

---

## Development Conventions

### Python Style
- Use `from __future__ import annotations` at the top of all files.
- Type hints on all function signatures.
- Use `Path` (not `str`) for file paths internally; accept `str | Path` in public APIs.
- Use `contextlib.closing` for connection lifecycle in `InventoryService`.
- Prefer `sqlite3.Row` dict-style access (`row["column"]`); always enabled via `row_factory`.

### Database Conventions
- Store timestamps as `TEXT` via SQLite `datetime('now','localtime')` — never Python datetime objects.
- Use `INTEGER` for boolean-like fields (e.g., `is_dir`): 0/1.
- Use `TEXT NOT NULL DEFAULT ''` for optional text fields that must not be NULL.
- Stock quantities are always `INTEGER`; cost values are `REAL`.
- Allocation `status` values: `reserved`, `consumed`, `released`.
- Transaction `doc_type` values: `IN`, `OUT`, `MOVE`, `ADJUST`, `CONSUME`, `RESERVE`, `RELEASE`.

### Adding New CLI Subcommands
1. Add `sub.add_parser(...)` in `main()` in `backend/app/inv.py`.
2. Add the handler logic in the `if args.cmd == "..."` block.
3. Add the corresponding business function(s) before `main()`.
4. If exposing via API: add a method to `InventoryService` in `core.py`, a Pydantic schema in `schemas.py`, and a route in `api.py`.

### Adding New Tables
1. Add DDL inside the `DDL` string in `backend/app/inv.py` using `CREATE TABLE IF NOT EXISTS`.
2. Add any indexes with `CREATE INDEX IF NOT EXISTS`.
3. Add any triggers with `CREATE TRIGGER IF NOT EXISTS` (use `DROP TRIGGER IF EXISTS` first only if replacing an existing trigger).
4. Test that running `init_db()` twice on the same DB does not error.

### XLSX Import/Export
- XLSX handling uses `openpyxl` (not pandas) for import.
- The standard transaction sheet name is `Transactions`; resource sheet is `Resources`.
- Import functions return `tuple[int, int]` → `(ok_count, err_count)`.
- API returns `ImportResponse(ok: int, err: int)`.

---

## Testing

```bash
# Run all tests
poetry run pytest

# Quick sanity check (no test framework needed)
python inv.py --help
```

No formal test suite exists beyond the scripts in `scripts/`. When adding features, verify manually with:
```bash
python inv.py --db ./lab_inventory.db proj-new --code TEST-001 --name "Test Project"
python inv.py --db ./lab_inventory.db proj-status --proj TEST-001
```

---

## Git Workflow

- Development branches follow the pattern: `claude/<session-id>`
- Commit messages use conventional format: `feat:`, `fix:`, `refactor:`, `docs:`
- Keep commits small and functional — each commit must leave `python inv.py --help` working.

---

## Common Pitfalls

- **Database locked errors**: If `lab_inventory.db` is open in DB Browser for SQLite (Windows), all writes will fail. The API returns HTTP 409 in this case.
- **Location must exist**: Before calling `reserve`, the location must exist in the `locations` table. Use `init-locations` or insert manually.
- **Over-reservation is hard-blocked**: The trigger fires at the DB level and raises `OperationalError`. Catch it and surface to the user.
- **`app/` shims only re-export**: Do not add business logic to `app/*.py` or `ui/streamlit_app.py`. All logic lives in `backend/` and `frontend/`.
- **The `connect()` in `backend/app/inv.py`** (line ~445) is a legacy function kept for direct CLI use; `backend/app/db.py`'s `connect()` is the canonical version used by the service layer. Both set the same PRAGMAs.
