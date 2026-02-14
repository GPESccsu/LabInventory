# AGENTS.md — LabInventory (SQLite) 元器件管理

## 目标
把当前仓库升级为“电子元件库存 + 出入库流水 + 可选项目归集 + XLSX 交互”的系统：
- **总库存**：按 part + location 维度维护库存（现有 stock 表）。
- **出入库**：必须可记录为流水；出/入库可以 **带项目**，也可以 **不带项目**（可选）。
- **兼容性**：保持现有 CLI 子命令可用，避免破坏既有数据库与脚本行为。

> 当前 inv.py 已包含核心表结构与项目预留/消耗流程（DDL 在 DDL 字符串里）。:contentReference[oaicite:1]{index=1}  
> 已有项目相关表：projects / proj:contentReference[oaicite:2]{index=2}预留”的触发器与项目物料状态视图。:contentReference[oaicite:3]{index=3} :contentReference[oaicite:4]{index=4} :contentReference[oaicite:5]{index=5}、:contentReference[oaicite:6]{index=6}子命令。:contentReference[oaicite:7]{index=7} :contentReference[oaicite:8]{index=8}:contentReference[oaicite:9]{index=9} :contentReference[oaicite:10]{index=10}，尤其是 DDL、库存函数、CLI 入口 main()。
- **小步提交**：每一步改动都要能运行（至少 `python inv.py --help` 不报错）。
- **数据库迁移**：若新增表/视图/触发器，必须是幂等（`IF NOT EXISTS`），并提供迁移路径（旧库打开后自动补齐）。
- **不要删表**：现有 tables/views/commands 不删除不改名；只能新增或兼容式扩展。

### 1. 兼容性红线（不许破坏）
- 保留 `--db` 参数与所有现有子命令名称/参数（例如 stock-in、proj-new、bom-set、reserve、release、consume、proj-status、proj-alloc、proj-forms）。:contentReference[oaicite:11]{index=11}
- 保留 Windows 路径兼容逻辑（resolve_:contentReference[oaicite:12]{index=12}ath）。:contentReference[oaicite:13]{index=13}
- `DDL` 必须继续作为“init_db 幂等初始化:contentReference[oaicite:14]{index=14}:contentReference[oaicite:15]{index=15} :contentReference[oaicite:16]{index=16}:contentReference[oaicite:17]{index=17} :contentReference[oaicite:18]{index=18}txn / stock_ledger），支持：
  - txn_type: IN / OUT / ADJUST
  - 可选 project_id（为空表示不带项目）
  - 记录 mpn/part_id、location、qty、note、created_at、operator（可选）
- 新增 **非项目出库**：例如 `stock-out` 子命令（不依赖 project_alloc）。
- 提供 **导出数据库结构（schema）** 的子命令：例如 `schema-export`（输出 .sql 或 .md），覆盖所有表/索引/视图/触发器。

P1（强烈建议）
- XLSX 交互：用一个固定格式的 xlsx 模板做批量入库/出库（可选 project_code），并提供导入校验与错误报告。
- 增加查询/报表：按项目、按库位、按 MPN 的库存与流水汇总视图/导出。

P2（可选）
- 操作员、审批、批次、供应商等字段扩展。

### 3. 工具与依赖
- Python 标准库优先；若必须新增依赖，需给出安装说明与最小化依赖理由。
- SQLite 为唯一数据库；优先使用 SQL 约束/触发器做一致性保护，Python 做业务编排。

### 4. 交付物
- 更新后的 inv.py（或拆分为 package，但 inv.py CLI 必须仍可作为入口）。
- 新增/更新：PLAN.md（本次执行计划落地）、README/使用说明（简短即可）。
- XLSX 模板与示例（若实现 XLSX 流程）。
