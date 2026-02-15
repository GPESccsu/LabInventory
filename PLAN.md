# PLAN.md — 项目资源挂接（本次落地）

## 已完成
- 在 `init_db()` 幂等 DDL 中新增：
  - `project_resources` 表（`project_id/type/name/uri/is_dir/tags/note/created_at/updated_at`）
  - 索引与唯一约束：`(project_id, type, uri)`
  - `trg_project_resources_updated` 触发器
  - `v_project_resources` / `v_project_overview` 视图
- 数据库连接增强：`timeout=30`、`WAL`、`busy_timeout=30000`。
- 新增 Python 资源模块：`app/project_resources.py`。
- CLI 新增层级命令：
  - `project add`
  - `project overview`
  - `project resource add/ls/rm/check/import-xlsx`
- 批量导入支持 `--sheet`、`--header-row`、`--auto-create-project`、`--no-check`。

## 兼容性
- 保留了所有既有命令与参数（`proj-new`、`bom-set`、`reserve`、`consume`、`proj-status`、`proj-alloc`、`schema-export` 等）。
- `inv.py` 顶层入口不变（`python inv.py ...`）。

## 待扩展（后续）
- `project resource open`（平台相关自动打开目录/文件）。
- 资源导入错误报告文件（JSON/CSV）。
