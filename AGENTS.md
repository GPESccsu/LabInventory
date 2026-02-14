# Agent Working Agreement (Codex)

## Guardrails
- Preserve backward compatibility:
  - Keep existing tables and views working: parts, stock, locations, projects, project_bom, project_alloc, v_project_material_status, v_project_alloc_detail.
  - Keep existing CLI commands working with same semantics.
- Avoid large rewrites. Prefer additive changes and small refactors.

## Required workflow
1) Read PLANS.md and inv.py (DDL + CLI).
2) Before changes, export schema: sqlite3 db ".schema" > docs/schema_before.sql
3) Implement in small steps. After each step run the smoke checks in PLANS.md.
4) After changes, export schema again: docs/schema_after.sql
5) Update docs and CLI help text.

## Quality bar
- All stock mutations must be transactional (BEGIN/COMMIT/ROLLBACK).
- Prevent negative stock on OUT/MOVE/CONSUME.
- Every stock change must be recorded in ledger tables.
