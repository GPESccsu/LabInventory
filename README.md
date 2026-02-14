# LabInventory

基于 **Python + SQLite** 的实验室物料库存与项目备料管理工具。

## 目录结构

```text
LabInventory/
├── app/                    # 主应用代码（CLI 核心）
│   └── inv.py
├── scripts/                # 辅助脚本
│   ├── import_bom.py       # 将 BoM xlsx 导入 parts（可抓 datasheet）
│   ├── lcsc_to_db.py       # 单个立创商品链接导入
│   ├── export_bom_parts_data.py
│   └── project_bom_allocation_example.py
├── docs/
├── data/
├── inv.py                  # 根目录入口（推荐）
└── lab_inventory.db
```

## 运行入口

- 推荐：`python inv.py ...`（可直接在仓库根目录运行）
- 等价：`python app/inv.py ...`

---

## 一、初始化与基础操作

### 1) 初始化库位

```bash
python inv.py --db ./lab_inventory.db init-locations \
  --room C409 --g01-shelves 3 --g02-shelves 1 --positions 10
```

### 2) 通过立创商品页导入单个器件（自动尝试下载 datasheet）

```bash
python inv.py --db ./lab_inventory.db lcsc \
  --url "https://item.szlcsc.com/8143.html" \
  --datasheets-dir ./datasheets
```

### 3) 手动入库

```bash
python inv.py --db ./lab_inventory.db stock-in \
  --mpn SN74LVC1G08DBVR --loc C409-G01-S01-P01 --qty 20

# 出库（可选关联项目）
python inv.py --db ./lab_inventory.db stock-out \
  --mpn SN74LVC1G08DBVR --loc C409-G01-S01-P01 --qty 5 --proj PJ-001

# 移库
python inv.py --db ./lab_inventory.db stock-move \
  --mpn SN74LVC1G08DBVR --from C409-G01-S01-P01 --to C409-G01-S01-P02 --qty 2

# 调整（必须填写 note；--add / --sub 二选一）
python inv.py --db ./lab_inventory.db stock-adjust \
  --mpn SN74LVC1G08DBVR --loc C409-G01-S01-P02 --sub 1 --note "盘点差异"

# 流水查询
python inv.py --db ./lab_inventory.db ledger --proj PJ-001 --mpn SN74LVC1G08DBVR --since 2026-01-01
```

---

## 二、项目流程（推荐）

### 1) 创建项目

```bash
python inv.py --db ./lab_inventory.db proj-new \
  --code PJ-001 --name "示例项目"
```

### 2) 手动维护项目 BOM（单条）

```bash
python inv.py --db ./lab_inventory.db bom-set \
  --proj PJ-001 --mpn SN74LVC1G08DBVR --req 10 --priority 2
```

### 3) 预留 / 释放 / 消耗

```bash
# 预留
python inv.py --db ./lab_inventory.db reserve \
  --proj PJ-001 --mpn SN74LVC1G08DBVR --loc C409-G01-S01-P01 --qty 5

# 释放
python inv.py --db ./lab_inventory.db release --id 1

# 消耗（会同时扣减 stock）
python inv.py --db ./lab_inventory.db consume --id 1
```

### 4) 查看项目状态

```bash
python inv.py --db ./lab_inventory.db proj-status --proj PJ-001
python inv.py --db ./lab_inventory.db proj-alloc  --proj PJ-001
```

---

## 三、`proj-forms`（按项目生成出/入库单）

### A. 项目模式（你最常用）

```bash
python inv.py --db ./lab_inventory.db proj-forms \
  --proj PJ-001 \
  --outbound-csv ./out/PJ-001-出库单.csv \
  --inbound-csv ./out/PJ-001-入库单.csv \
  --lcsc-file ./BoM报价-立创_20260212.xlsx
```

当同时提供 `--proj` + `--lcsc-file` 时，会执行：

1. 自动确保 `projects` 里存在该项目（不存在则创建）。
2. 依据 xlsx 更新/写入 `parts`。
3. **覆盖**该项目 `project_bom`（删除旧记录，再按 xlsx 重建）。
4. 生成出库单/入库单 CSV。

可选直接入库：

```bash
python inv.py --db ./lab_inventory.db proj-forms \
  --proj PJ-001 \
  --outbound-csv ./out/PJ-001-出库单.csv \
  --inbound-csv ./out/PJ-001-入库单.csv \
  --lcsc-file ./BoM报价-立创_20260212.xlsx \
  --apply-inbound --inbound-loc C409-G01-S01-P01
```

### B. 仅导入立创文件到 `parts + stock`

```bash
python inv.py --db ./lab_inventory.db proj-forms \
  --lcsc-file ./BoM报价-立创_20260212.xlsx \
  --inbound-loc LCSC-INBOX
```

---

## 四、字段映射（当前实现）

### 1) `parts` 表映射（xlsx -> parts）

- `mpn` ← `Manufacturer Part` / `型号`
- `name` ← `商品名称`
- `category` ← `目录`（缺失时回退分类相关列）
- `package` ← `封装`
- `params` ← `参数`
- `note` ← `Manufacturer`
- `url` ← `商品链接`

> 支持 pandas 自动重命名列（如 `Manufacturer.1`、`商品链接.1`、`参数.1`）。

### 2) `PJ-001-入库单.csv` / `PJ-001-出库单.csv` 映射

- `序号` ← `parts.id`
- `时间` ← 当天日期（`YYYY.MM.DD`）
- `名称` ← `mpn`
- `型号规格` ← `parts.name`
- `单位` ← `parts.unit`
- `数量` ← `购买数量`
- `单价(元)` ← `单价(RMB)`
- `总额(元)` ← `数量 × 单价(元)`

---

## 五、独立导入脚本（`scripts/import_bom.py`）

用于将 BoM xlsx 直接导入 `parts`（支持 dry-run、日志、datasheet 下载）：

```bash
python scripts/import_bom.py \
  --db ./lab_inventory.db \
  --xlsx ./BoM报价-立创_20260212.xlsx \
  --sheet 0 \
  --log ./import_log.txt \
  --datasheets-dir ./datasheets
```

只校验不提交：

```bash
python scripts/import_bom.py \
  --db ./lab_inventory.db \
  --xlsx ./BoM报价-立创_20260212.xlsx \
  --dry-run
```

---

## 六、建议流程

1. `init-locations` 初始化库位。
2. 用 `proj-forms --proj ... --lcsc-file ...` 导入项目并覆盖 `project_bom`。
3. 生成 `出库单/入库单`，按实际流程领料和到货。
4. 需要时 `--apply-inbound` 自动入库。
5. 用 `proj-status / proj-alloc` 持续检查备料与预留状态。
