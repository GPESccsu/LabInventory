# LabInventory

C409 实验室元器件库存管理系统。基于 SQLite 单文件数据库，提供三种操作界面：

- **CLI**：`python inv.py --db <路径> <子命令>`，适合批量操作与脚本集成
- **FastAPI 后端**：HTTP REST API，供前端和外部程序调用
- **Streamlit 前端**：中文 Web UI，支持库存管理、物料查询、项目管理、流水查询等

三个界面共享同一个数据库文件，数据实时一致。

---

## 目录结构

```
LabInventory/
├── backend/app/
│   ├── inv.py              # CLI 业务逻辑与 main()
│   ├── db.py               # SQLite connect() / init_db()
│   ├── core.py             # InventoryService（供 API 调用）
│   ├── schemas.py          # Pydantic 请求/响应模型
│   ├── api.py              # FastAPI 路由
│   └── project_resources.py # 项目资源 CRUD + XLSX 导入
├── frontend/
│   └── streamlit_app.py    # Streamlit Web UI
├── app/                    # 兼容层（转发到 backend.app）
├── ui/                     # 兼容层（转发到 frontend）
├── inv.py                  # CLI 兼容入口
├── tests/                  # 自动化测试
├── scripts/                # 辅助脚本（BOM 导入、LCSC 抓取等）
├── data/reference/         # 参考数据（库位 CSV、物料模板等）
├── docs/                   # 文档与 schema 快照
└── lab_inventory.db        # SQLite 数据库（WAL 模式）
```

---

## 安装

需要 Python ≥ 3.11，使用 [Poetry](https://python-poetry.org/) 管理依赖。

```bash
poetry install
```

### 可选依赖说明

`poetry install` 会安装全部依赖（包括 LCSC 抓取和 XLSX 导入所需的包）。

- **核心 CLI**（库存/项目/流水/Schema 等）不需要 `requests`、`beautifulsoup4` 或 `openpyxl`，可在最小依赖环境下正常运行。
- **LCSC 导入**（`lcsc` 子命令）需要 `requests` + `beautifulsoup4`；缺少时执行该命令会提示安装方法。
- **XLSX 导入导出**（`txn-export-xlsx`、`txn-import-xlsx`）需要 `openpyxl`；缺少时同样会提示安装方法。

---

## 启动

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LABINV_DB` | `./lab_inventory.db` | 数据库文件路径（FastAPI 使用） |
| `LABINV_API_BASE` | `http://127.0.0.1:8000` | API 地址（Streamlit 使用） |

### FastAPI 后端

```bash
poetry run uvicorn backend.app.api:app --host 0.0.0.0 --port 8000
```

启动后可访问交互式文档：`http://localhost:8000/docs`

### Streamlit 前端

```bash
# 新开终端
poetry run streamlit run frontend/streamlit_app.py
```

默认访问地址：`http://localhost:8501`

### CLI

```bash
python inv.py --db ./lab_inventory.db --help
```

---

## CLI 子命令速查

### 初始化库位


```bash
# 按 C409 房间规格生成标准库位编码（G01 三层 / G02 一层 / 每层 10 位）
python inv.py --db ./lab_inventory.db init-locations --room C409
```

### 物料入库

```bash
python inv.py --db ./lab_inventory.db stock-in \
  --mpn SN74LVC1G08DBVR --loc C409-G01-S01-P01 --qty 100 \
  --condition new --note "首次采购"
```

### 物料出库

```bash
python inv.py --db ./lab_inventory.db stock-out \
  --mpn SN74LVC1G08DBVR --loc C409-G01-S01-P01 --qty 10 \
  --proj PJ-001 --operator 张三
```

### 移库

```bash
python inv.py --db ./lab_inventory.db stock-move \
  --mpn SN74LVC1G08DBVR --from C409-G01-S01-P01 --to C409-G01-S02-P03 --qty 50
```

### 库存调整（盘点修正）

```bash
python inv.py --db ./lab_inventory.db stock-adjust \
  --mpn SN74LVC1G08DBVR --loc C409-G01-S01-P01 --sub 2 --note "盘点少了2个"
```

### 项目管理

```bash
# 创建项目
python inv.py --db ./lab_inventory.db proj-new --code PJ-001 --name "智能小车" --owner 李四

# 设置 BOM
python inv.py --db ./lab_inventory.db bom-set --proj PJ-001 --mpn SN74LVC1G08DBVR --req 20

# 查看备料状态
python inv.py --db ./lab_inventory.db proj-status --proj PJ-001

# 预留物料
python inv.py --db ./lab_inventory.db reserve \
  --proj PJ-001 --mpn SN74LVC1G08DBVR --loc C409-G01-S01-P01 --qty 20

# 查看预留明细（记录 alloc_id）
python inv.py --db ./lab_inventory.db proj-alloc --proj PJ-001

# 消耗（扣减库存）/ 释放预留
python inv.py --db ./lab_inventory.db consume --id 1
python inv.py --db ./lab_inventory.db release --id 2
```

### 项目资源挂接

```bash
# 添加文件/URL 资源
python inv.py --db ./lab_inventory.db project resource add \
  --code PJ-001 --type doc --name "原理图" --uri "G:\Projects\PJ-001\sch.pdf"

# 列出资源
python inv.py --db ./lab_inventory.db project resource ls --code PJ-001

# 检查资源路径有效性
python inv.py --db ./lab_inventory.db project resource check --code PJ-001

# 从 XLSX 批量导入资源
python inv.py --db ./lab_inventory.db project resource import-xlsx \
  --xlsx resources.xlsx --auto-create-project
```

### 从立创商城导入物料

```bash
# 自动抓取物料参数并下载数据手册
python inv.py --db ./lab_inventory.db lcsc \
  --url https://item.szlcsc.com/7666.html \
  --datasheets-dir ./datasheets
```

### 流水查询

```bash
# 全部流水
python inv.py --db ./lab_inventory.db ledger

# 按项目/物料/日期筛选
python inv.py --db ./lab_inventory.db ledger --proj PJ-001 --mpn SN74LVC1G08DBVR --since 2026-01-01
```

### XLSX 导入导出

```bash
# 导出交易模板
python inv.py --db ./lab_inventory.db txn-export-xlsx --out template.xlsx

# 导入交易（支持 auto / transactions / stock-io 三种模式）
python inv.py --db ./lab_inventory.db txn-import-xlsx --xlsx records.xlsx --mode auto

# 生成项目出入库单 CSV
python inv.py --db ./lab_inventory.db proj-forms --proj PJ-001 \
  --outbound-csv out/出库单.csv --inbound-csv out/入库单.csv
```

### 数据库结构导出

```bash
python inv.py --db ./lab_inventory.db schema-export --format md --out docs/schema.md
```

---

## API 端点速查

基础地址：`http://localhost:8000`

### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查，返回物料数/库存行数/项目数 |

### 物料

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/parts?query=` | 搜索物料（MPN/名称/类别/封装） |

### 库存

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/stock?query=&location=` | 查询库存 |
| POST | `/api/stock/in` | 入库 |
| POST | `/api/stock/out` | 出库 |
| POST | `/api/stock/move` | 移库 |
| POST | `/api/stock/adjust` | 库存调整 |
| GET | `/api/locations` | 列出所有库位 |

### 流水

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ledger?project=&mpn=&since=` | 查询库存流水 |

### 项目

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects` | 创建/更新项目 |
| GET | `/api/projects?query=` | 列出项目 |
| GET | `/api/projects/{code}` | 获取项目详情 |
| GET | `/api/projects/{code}/status` | BOM + 库存 + 预留状态 |
| GET | `/api/projects/{code}/allocs` | 预留明细 |
| POST | `/api/projects/{code}/bom` | 批量设置 BOM |
| POST | `/api/projects/{code}/reserve` | 预留物料 |
| POST | `/api/allocs/{id}/release` | 释放预留 |
| POST | `/api/allocs/{id}/consume` | 消耗预留 |

### 项目资源

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects/{code}/resources` | 新增/更新资源 |
| GET | `/api/projects/{code}/resources` | 列出资源 |
| DELETE | `/api/projects/{code}/resources` | 删除资源 |
| POST | `/api/projects/{code}/resources/check` | 检查资源路径有效性 |
| POST | `/api/projects/resources/import-xlsx` | 从 XLSX 批量导入资源 |

### XLSX 导入

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/txns/import-xlsx` | 批量导入交易记录 |

**HTTP 状态码：**`400` 业务错误 / `404` 资源不存在 / `409` 数据库被锁定

---

## Web UI 功能标签页

| 标签页 | 功能 |
|--------|------|
| 库存管理 | 库存查询（按 MPN / 库位筛选）+ 入库 / 出库 / 移库 / 调整操作表单 |
| 物料查询 | 按 MPN、名称、类别、封装全文搜索，显示物料清单 |
| 项目管理 | 项目列表与新建、BOM + 库存状态、执行预留、释放 / 消耗 |
| 项目资源 | 新增 / 删除 / 检查项目关联的文件路径或 URL |
| 库存流水 | 按项目、MPN、起始日期筛选历史交易记录 |
| XLSX 导入 | 上传交易或项目资源 XLSX 文件进行批量导入 |

侧边栏实时显示：物料种类、有库存记录数、项目数。

---

## 数据库设计要点

- **WAL 模式**：`journal_mode=WAL`，读写并发更好
- **外键约束**：`foreign_keys=ON`，数据一致性有保障
- **超预留硬阻断**：数据库触发器 `trg_alloc_no_overreserve_ins/upd` 在 DB 层阻止超额预留，无法绕过
- **库位必须预先存在**：执行预留前，库位须在 `locations` 表中注册（用 `init-locations` 初始化）
- **时间戳**：统一存为 `TEXT`（`datetime('now','localtime')`），不依赖 Python datetime

主要表：`parts`、`stock`、`locations`、`projects`、`project_bom`、`project_alloc`、`inv_doc`、`inv_line`、`project_resources`

---

## 运行测试

```bash
poetry run pytest
```

测试覆盖核心服务层（`test_core.py`）、API 端点（`test_api.py`）、CLI 入口（`test_cli.py`），共 36 个用例。

---

## 常见问题

**Q：写入时报"数据库被锁定"？**
A：关闭正在占用数据库的程序（如 DB Browser for SQLite），API 返回 HTTP 409。

**Q：预留失败报超预留错误？**
A：当前可用库存不足，需先入库或释放其他项目的预留。

**Q：Windows 下如何指定数据库路径？**
A：直接传入 Windows 路径即可，CLI 内部已处理转义：
```bash
python inv.py --db "G:\LabInventory\lab_inventory.db" proj-status --proj PJ-001
```
