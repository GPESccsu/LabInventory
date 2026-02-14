# PLAN.md — 电子元件库存：出入库（可选项目）+ 流水 + XLSX

本计划面向“没有上下文的实现者”，要求按步骤交付可运行结果。
参考：Codex ExecPlans/PLANS.md 的写法（强调可执行步骤与验收）。(external)

## 背景（现状）
- 当前 DB 在 inv.py 内通过 DDL 初始化：parts / stock / locations + projects / project_bom / project_alloc，并含视图与触发器。:contentReference[oaicite:19]{index=19} :contentReference[oaicite:20]{index=20}:contentReference[oaicite:21]{index=21}:contentReference[oaicite:22]{index=22}
:contentReference[oaicite:23]{index=23}要:contentReference[oaicite:24]{index=24}。:contentReference[oaicite:25]{index=25}
- 用户需求：新增“非项目出库/入库可选项目”，并且希望可:contentReference[oaicite:26]{index=26}必须实现）
1) 新增“统一流水”：任何入库/出库/调整都落库一条交易记录（可追溯）。
2) 新增“非项目出库”：不需要 project，也能从 stock 扣减，并写流水。
3) 保持现有项目流程不破坏：reserve/release/consume 仍可用，且继续受“禁止超预留”保护。
4) 新增“导出 schema”：一条命令输出 DB 结构（表/索引/视图/触发器），便于备份/审计。
5) 提供 XLSX 批量交易入口：按模板导入多行交易（可选 project_code）。

## 非目标（本期不做）
- 不做 Web UI；不引入服务端框架。
- 不做复杂权限/审批流（可留扩展点）。

## 数据模型改造（建议方案）
新增表（命名可调整，但必须满足字段语义）：

A. inventory_txn（交易主表）
- id (PK)
- txn_type: 'IN' | 'OUT' | 'ADJUST'
- project_id (NULLABLE) — 可为空表示不归集到项目
- ref (TEXT) — 外部单据号/批次号（可选）
- note (TEXT)
- created_at

B. inventory_txn_line（交易明细）
- id (PK)
- txn_id (FK -> inventory_txn.id)
- part_id (FK -> parts.id)
- mpn_snapshot (TEXT) — 防止未来 mpn 改名追溯困难（可选）
- location (TEXT, nullable: 某些调整可能不指定库位；但 IN/OUT 推荐强制 location)
- qty_delta (INTEGER) — 入库为正，出库为负
- condition (TEXT) — 继承 stock.condition 语义（可选）
- note

一致性要求：
- 对 IN/OUT：写入 txn_line 后，必须同步更新 stock（插入或更新对应 part_id+location）。
- 对 OUT：必须校验扣减后不为负；若负则整笔事务回滚。
- 如果提供 project_code：要能映射到 projects.id；找不到则报错（除非显式允许自动创建）。

## CLI 改造（兼容 + 新增）
必须保留现有命令；新增命令建议：
- `stock-out`：非项目出库（--mpn --loc --qty --note，可选 --proj）
- `txn-import-xlsx`：导入 xlsx 交易（支持 IN/OUT，且 project 可空）
- `txn-export-xlsx`：导出模板/导出某段时间流水
- `schema-export`：导出 schema（--format sql|md --out path）

## XLSX 模板（最小可用）
建议一个 sheet：Transactions
列建议：
- txn_type (IN/OUT/ADJUST)
- project_code (可空)
- mpn
- location
- qty (正数输入；由 txn_type 决定正负)
- condition (可选)
- note

导入规则：
- 逐行校验，错误写到 ErrorReport sheet 或输出一个 .csv/.json 报告；
- 允许“部分成功”或“全有全无”二选一（建议默认全有全无，--partial 可开启部分成功）。

---

# ✅ Codex 可执行 Checklist（逐步执行）

## Phase 0 — 基线与理解
- [x] 读取 inv.py，梳理：DDL、现有表/视图/触发器、现有库存函数、CLI 子命令与参数。
- [x] 在不改代码的情况下运行：
  - [x] `python inv.py --db /tmp/phase0.db --help`（确保可运行）
  - [x] 找一个空 db 路径执行初始化流程（若仓库已有 init 命令则用；否则运行触发 init_db 的现有路径）
- [x] 记录当前 schema 关键点（parts/stock/locations/projects/project_bom/project_alloc + views）。

### Phase 0 输出：Phase 1 具体改动点（文件 / 函数 / 表结构）

1) 文件级改动
- `app/inv.py`
  - 在现有 `DDL` 末尾新增：
    - `inventory_txn`（交易主表，`txn_type/project_id/ref/note/operator/created_at`）
    - `inventory_txn_line`（交易明细，`txn_id/part_id/mpn_snapshot/location/qty_delta/condition/note`）
    - 新索引（`txn_type`、`created_at`、`project_id`、`part_id`、`location`）
  - 新增 `apply_migrations(conn)` 并在 `main()` 中 `init_db(conn)` 后调用，保证旧库自动补齐。
  - 新增 DAO：
    - `create_txn(conn, txn_type, project_code=None, ref='', note='', operator='') -> int`
    - `add_txn_line(conn, txn_id, mpn, location, qty_delta, condition='new', note='') -> int`
  - 抽取统一库存写入函数（建议 `apply_stock_delta(...)`），由 `stock_in/stock_out/stock_adjust/stock_move` 复用，确保事务一致性。

2) 事务与一致性
- 统一使用 `_tx_begin/_tx_commit/_tx_rollback` 包裹“主单 + 明细 + stock 更新”，任何一步失败整笔回滚。
- `OUT` 场景在写库前先校验 `stock.qty + qty_delta >= 0`，不足直接抛错；保证不会留下半条交易。

3) 兼容策略
- 保留现有 `inv_doc/inv_line` 写入逻辑不删不改名（短期双写）。
- 保留现有 CLI 子命令和参数（尤其 `stock-in/stock-out/proj-*`）。
- 保留 `resolve_input_path/resolve_output_path` Windows 路径兼容逻辑。

## Phase 1 — 引入交易流水表（不影响旧逻辑）
- [x] 在 DDL 中新增 inventory_txn 与 inventory_txn_line（幂等）。
- [x] 写一个 `apply_migrations(conn)`（或复用 init_db）保证旧库打开也能补齐新表。
- [x] 新增最小 DAO 函数：
  - [x] `create_txn(conn, txn_type, project_code|None, ref, note) -> txn_id`
  - [x] `add_txn_line(conn, txn_id, mpn, location, qty_delta, condition, note)`
- [x] 用 SQLite 事务包裹：创建 txn + lines + 更新 stock 必须原子提交。

验收：
- [x] 新建空库，能看到新增表存在（通过 sqlite_master 或 schema-export 验证）。

## Phase 2 — 实现非项目出库 + 可选项目出入库（核心）
- [x] 新增 `stock-out` 子命令：
  - [x] 参数：--mpn --loc --qty(正数) [--proj 可选] [--note]
  - [x] 实现：写 txn (type OUT) + line(qty_delta = -qty) + 更新 stock 扣减
  - [x] 校验：库存不足则报错并回滚
- [x] 改造现有 `stock-in`：
  - [x] 保持原功能输出不变
  - [x] 额外写入 txn(type IN)（project 可选，默认空）
- [x] 不改 reserve/release/consume 的业务语义，但建议在 consume 成功后补写 txn(type OUT, project=必填) 作为“项目领用流水”（可选但强烈建议）。

验收：
- [x] stock-in 后，stock 增加且 txn/line 有记录。
- [x] stock-out 后，stock 减少且 txn/line 有记录。
- [x] 库存不足时 stock-out 必须失败且不留下半条 txn。
- [x] reserve/consume 旧命令仍可运行（兼容性）。

## Phase 3 — schema-export（导出结构）
- [x] 新增 `schema-export` 子命令：
  - [x] sql 模式：输出 `SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name;`
  - [x] md 模式：表格列出 tables/views/indexes/triggers + 关键字段（可从 PRAGMA table_info 取）
- [x] 支持 --out 输出到文件；不提供 --out 则打印到 stdout。

验收：
- [x] 能导出包含 parts/stock/.../views/triggers 的完整结构。

## Phase 4 — XLSX 交易导入/导出（可选项目）
- [x] 引入 xlsx 读写（openpyxl 优先；若已存在模板则复用格式）。
- [x] 新增 `txn-import-xlsx`：
  - [x] 读取 Transactions sheet
  - [x] 逐行校验并映射到 txn/lines（建议：同一批导入形成一个 ref 批次号）
  - [x] 默认“全有全无”，遇错回滚并生成 ErrorReport
- [x] 新增 `txn-export-xlsx`：
  - [x] 导出空模板（或复制仓库内模板）
  - [ ] 可选导出某时间段流水到 xlsx（便于人工审计）

验收：
- [x] 给一份 2 行 IN + 2 行 OUT 的 xlsx，导入后库存与流水一致。
- [x] 错误行能被明确报出（行号/字段/原因）。

## Phase 5 — 文档与示例
- [x] 更新 README：给出 3 个最常用流程：
  - [x] 非项目入库/出库（stock-in/stock-out）
  - [x] 项目流程（proj-new、bom-set、reserve、consume）
  - [x] XLSX 批量导入
- [x] 给出“导出 schema”用法示例与输出示例片段。

---

## 最终验收标准（Definition of Done）
- [x] 旧库可直接打开并自动补齐新表（不需要手工迁移）。
- [x] 现有命令不改名不失效；新增命令可用。
- [x] 任何一次入/出库都能在流水表追溯到：时间、数量、库位、（可选）项目。
- [x] schema-export 输出包含所有表/索引/视图/触发器。
- [x] XLSX 导入能稳定工作并给出可读错误报告。
