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
│       ├── project_resources.py # Project resource CRUD + XLSX import
│       ├── llm_service.py      # LLMService facade (business layer LLM entry point)
│       └── llm/                # LLM integration layer
│           ├── __init__.py     # get_provider() factory + re-exports
│           ├── config.py       # LLMConfig (env-based)
│           ├── base.py         # BaseLLMProvider abstract class
│           ├── mock_provider.py # Mock provider (keyword/regex, no deps)
│           ├── local_provider.py # Local LLM (Ollama/vLLM via OpenAI-compat API)
│           ├── cloud_provider.py # Cloud LLM (OpenAI/Anthropic/DeepSeek)
│           ├── intent.py       # Intent enum + ParsedIntent + parse_intent()
│           ├── summarizer.py   # summarize_result() helper
│           ├── query_executor.py # ParsedIntent → real DB query execution
│           ├── draft_builder.py # ParsedIntent → stock operation draft (no execute)
│           └── resource_qa.py  # Project resource Q&A via LLM
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
├── tests/                      # Automated tests (pytest)
│   ├── conftest.py             # Shared fixtures (tmp DB, test client)
│   ├── test_core.py            # InventoryService unit tests
│   ├── test_api.py             # FastAPI endpoint tests
│   ├── test_cli_smoke.py       # CLI --help smoke tests
│   ├── test_api_import.py      # API import + schema completeness
│   └── test_txn_integrity.py   # Transaction integrity tests
├── data/                       # Reference data and templates
│   └── reference/              # locations CSV, parts data, resource templates
├── schema/                     # DB schema JSON snapshots
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
| `LABINV_LLM_PROVIDER` | `mock` | LLM provider: `mock` / `local` / `cloud` |
| `LABINV_LLM_MODEL` | `""` | Model name (e.g. `qwen2.5:7b`, `claude-sonnet-4-20250514`) |
| `LABINV_LLM_API_BASE` | `http://localhost:11434` | LLM API base URL |
| `LABINV_LLM_API_KEY` | `""` | API key for cloud providers |
| `LABINV_LLM_API_TYPE` | `openai` | API type: `openai` / `anthropic` / `deepseek` |
| `LABINV_LLM_TIMEOUT` | `30` | Request timeout in seconds |
| `LABINV_LLM_MAX_TOKENS` | `2048` | Max generation tokens |

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
```

---

## FastAPI Endpoints (`backend/app/api.py`)

Base URL: `http://0.0.0.0:8000`

### System & Data

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (parts/stock/project counts) |
| GET | `/api/parts?query=` | Search parts by MPN/name/category/package |
| GET | `/api/stock?query=&location=` | Query stock levels |
| POST | `/api/stock/in` | Stock in |
| POST | `/api/stock/out` | Stock out |
| POST | `/api/stock/move` | Stock move |
| POST | `/api/stock/adjust` | Stock adjust |
| GET | `/api/locations` | List all locations |
| GET | `/api/ledger?project=&mpn=&since=` | Query transaction ledger |
| GET | `/api/txns/export-template` | Download XLSX transaction template |
| POST | `/api/txns/import-xlsx` | Batch import transactions from XLSX |

### Projects

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/projects` | Create or update a project |
| GET | `/api/projects` | List projects (optional `?query=`) |
| GET | `/api/projects/{code}` | Get project detail |
| GET | `/api/projects/{code}/status` | Project BOM+stock+alloc status |
| GET | `/api/projects/{code}/allocs` | Project allocation details |
| POST | `/api/projects/{code}/bom` | Set project BOM (batch) |
| POST | `/api/projects/{code}/reserve` | Reserve parts for a project |
| POST | `/api/allocs/{id}/release` | Release an allocation |
| POST | `/api/allocs/{id}/consume` | Consume an allocation |

### Project Resources

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/projects/{code}/resources` | Add/update a project resource |
| GET | `/api/projects/{code}/resources` | List project resources |
| DELETE | `/api/projects/{code}/resources` | Delete a project resource |
| POST | `/api/projects/{code}/resources/check` | Check resource URI validity |
| POST | `/api/projects/{code}/resources/qa` | Resource Q&A (LLM-powered) |
| POST | `/api/projects/resources/import-xlsx` | Batch import resources from XLSX |

### LCSC Import

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/lcsc/fetch` | Fetch part data from LCSC URL |
| POST | `/api/lcsc/import-xlsx` | Batch import from LCSC XLSX |

### LLM / Natural Language

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/llm/chat` | LLM multi-turn chat |
| POST | `/api/llm/intent` | Intent classification + field extraction |
| GET | `/api/llm/config` | Current LLM provider config (safe view) |
| POST | `/api/llm/ping` | Test LLM provider connectivity |
| POST | `/api/llm/parse` | Intent parse + fields + summary (one call) |
| POST | `/api/llm/query` | NL → real DB query → Chinese result |
| POST | `/api/llm/draft-stock-op` | NL → stock operation draft (no execute) |
| POST | `/api/llm/execute-draft` | Confirm and execute a draft operation |

### Error HTTP Status Codes

- `404` — `NotFoundError` (project/part not found)
- `409` — `DatabaseLockedError` (SQLite busy)
- `400` — all other `InventoryError` variants

---

## Code Architecture

### Layering

```
CLI (inv.py main)          Streamlit UI (HTTP client)
        │                           │
        ▼                           ▼ (HTTP)
backend/app/inv.py         FastAPI (backend/app/api.py)
  business functions               │
        │                    ┌─────┴──────┐
        │                    ▼            ▼
        │            LLMService     InventoryService
        │          (llm_service.py)   (core.py)
        │                │            │
        │          llm/ package       │
        │          (providers,        │
        │           intent, query)    │
        │                             │
        └──────────── backend/app/inv.py (shared functions)
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

## LLM Integration (`backend/app/llm/`)

### Architecture

```
User natural language input
        │
        ▼
  parse_intent(provider, text)      ← intent.py
        │
        ├── classify_intent()       ← BaseLLMProvider method
        └── extract_fields()        ← BaseLLMProvider method
        │
        ▼
  ParsedIntent { intent, params, missing_fields }
        │
        ▼
  InventoryService (existing)       ← core.py (unchanged)
        │
        ▼
  summarize_result(provider, ...)   ← summarizer.py
```

### LLM Service Facade

`LLMService` (`backend/app/llm_service.py`) is the **single entry point** for all LLM operations. Business code (API routes) only imports `llm_service`, never directly touches providers or config. Key methods:
- `chat(messages)` → multi-turn conversation
- `parse(text)` → intent + field extraction → `ParsedIntent`
- `query(text)` → NL → real DB query → structured result with Chinese message
- `draft_stock_op(text)` → NL → stock operation draft (not executed)
- `execute_draft(op, fields)` → confirm and execute a draft via InventoryService
- `resource_qa(project_code, question)` → project resource Q&A
- `ping()` → test provider connectivity

### Provider Abstraction

`BaseLLMProvider` (`base.py`) defines four abstract methods + `chat_json()` utility:
- `chat(messages)` → multi-turn conversation
- `classify_intent(text, candidates)` → intent string
- `extract_fields(text, field_schema)` → extracted params dict
- `summarize(data, instruction)` → Chinese text summary
- `chat_json(system_prompt, user_prompt, schema_hint)` → structured JSON output (shared)

Current implementations:
- **`MockProvider`** — keyword/regex matching, zero external dependencies. Default (`LABINV_LLM_PROVIDER=mock`).
- **`LocalProvider`** — calls local models via OpenAI-compatible API (Ollama/vLLM/LocalAI). Set `LABINV_LLM_PROVIDER=local`.
- **`CloudProvider`** — calls cloud APIs (OpenAI/Anthropic/DeepSeek). Set `LABINV_LLM_PROVIDER=cloud` + `LABINV_LLM_API_KEY`.

### Query & Draft Workflow

```
User NL input
      │
      ▼
  parse_intent()           → ParsedIntent { intent, params, missing_fields }
      │
      ├─ Query intents ──→ execute_query()  → real DB data + Chinese message
      │                      (query_executor.py)
      │
      └─ Write intents ──→ build_draft()    → operation draft (NOT executed)
                             (draft_builder.py)
                                   │
                             user confirms
                                   │
                                   ▼
                           execute_draft()   → InventoryService (real execution)
```

### Intent System

`Intent` enum in `intent.py` covers: `stock_in`, `stock_out`, `stock_move`, `stock_adjust`, `reserve`, `release`, `consume`, `query_stock`, `query_parts`, `query_ledger`, `project_status`, `help`, `unknown`.

Each intent has a `field_schema` (what fields to extract) and `required_fields` (what must be present for the action to execute). `ParsedIntent.is_complete` checks all required fields are filled.

### Adding a New LLM Provider

1. Create `backend/app/llm/<name>_provider.py` implementing `BaseLLMProvider`.
2. Add a branch in `get_provider()` in `__init__.py`.
3. User sets `LABINV_LLM_PROVIDER=<name>` and related env vars.

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

# Run with verbose output
poetry run pytest -v

# Quick sanity check (no test framework needed)
python inv.py --help
```

Test suite (`tests/`):
- **`test_core.py`** — InventoryService unit tests (stock ops, projects, BOM, alloc)
- **`test_api.py`** — FastAPI endpoint integration tests (requires fastapi/httpx)
- **`test_cli_smoke.py`** — CLI `--help` smoke tests for all subcommands
- **`test_api_import.py`** — API module import + schema completeness checks
- **`test_txn_integrity.py`** — Transaction integrity and edge case tests

### Minimum acceptance checks
```bash
python inv.py --help                              # CLI entry point works
poetry run python -c "import backend.app.api"     # API imports without error
poetry run pytest -v                              # All tests pass
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
