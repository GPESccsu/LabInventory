# LabInventory

这是一个基于 **Python + SQLite** 的实验室物料库存与项目备料管理工具。

## 重构后的目录结构

```text
LabInventory/
├── app/                    # 主应用代码
│   └── inv.py              # 主 CLI（推荐入口）
├── scripts/                # 辅助/一次性脚本
│   ├── lcsc_to_db.py
│   ├── import_bom.py
│   ├── project_bom_allocation_example.py
│   └── export_bom_parts_data.py
├── docs/                   # 文档与命令示例
│   └── 命令.txt
├── data/
│   ├── db/                 # 数据库文件建议放置位置
│   ├── raw/                # 原始导入文件建议放置位置
│   └── reference/          # 参考数据（库位模板等）
├── datasheets/             # 数据手册 PDF
├── inv.py                  # 兼容入口（转发到 app/inv.py）
└── lcsc_to_db.py           # 兼容入口（转发到 scripts/lcsc_to_db.py）
```

## 入口说明

- 推荐使用：`python inv.py ...`
- 新路径也可用：`python app/inv.py ...`
- 为兼容旧习惯保留了根目录 `inv.py` 与 `lcsc_to_db.py` 转发入口。

## 管理建议

1. 业务逻辑只放在 `app/`。
2. 一次性脚本统一收敛到 `scripts/`。
3. 命令示例、操作手册放在 `docs/`。
4. 新增数据文件优先放 `data/` 下对应子目录，避免根目录继续堆积。

## 脚本重命名说明

- `scripts/script_name.py` → `scripts/export_bom_parts_data.py`（用于从 BOM Excel 提取并导出 `parts_data.txt`）。
- `scripts/pro_exp.py` → `scripts/project_bom_allocation_example.py`（用于项目创建、BOM 添加与库存预留示例）。

## 项目出入库单自动填写（新增）

当前 `inv.py` 已支持按项目自动生成出库/入库单（CSV）：

- 命令：`proj-forms`
- 设计要点：
  - 出库单基于项目 BOM 生成，**数量列默认留空**（后续人工填写）。
  - 入库单优先读取立创导出文件（`csv/xlsx/xls`），不提供时回退为项目 BOM 需求数量。
  - 可选将入库单数量直接写入库存（需指定库位）。

### 快速示例

仅生成单据：

```bash
python inv.py --db ./lab_inventory.db proj-forms \
  --proj PJ-001 \
  --outbound-csv ./out/PJ-001-出库单.csv \
  --inbound-csv ./out/PJ-001-入库单.csv \
  --lcsc-file ./BoM报价-立创_20260212.xlsx
```

生成并直接入库：

```bash
python inv.py --db ./lab_inventory.db proj-forms \
  --proj PJ-001 \
  --outbound-csv ./out/PJ-001-出库单.csv \
  --inbound-csv ./out/PJ-001-入库单.csv \
  --lcsc-file ./BoM报价-立创_20260212.xlsx \
  --apply-inbound --inbound-loc C409-G01-S01-P01
```

### 推荐流程

1. 先按项目生成出库单（数量空白）。
2. 人工填写本次实际出库数量。
3. 再根据填写结果执行出库扣减。
4. 到货后用立创数据生成入库单并验收。
5. 通过 `--apply-inbound`（可选）将确认数量写入库存。

详细说明见：`docs/项目出入库单自动填写说明.md`。
