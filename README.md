# LabInventory（CLI + FastAPI + Streamlit）

本项目基于 SQLite，保留原有 `inv.py` CLI 能力，并新增：
- FastAPI 后端（HTTP API）
- Streamlit 前端（中文 Web UI）
- 统一的 API 数据模型定义：`app/schemas.py`

## 1. 安装依赖（Poetry）

```bash
poetry install
```

## 2. 启动方式

> 默认数据库路径：`./lab_inventory.db`。
> 可通过环境变量覆盖：`LABINV_DB=/path/to/xxx.db`。

### 启动 FastAPI

```bash
poetry run uvicorn app.api:app --host 0.0.0.0 --port 8000
```

### 启动 Streamlit

```bash
poetry run streamlit run ui/streamlit_app.py
```

> Streamlit 默认调用 `http://127.0.0.1:8000`，可通过 `LABINV_API_BASE` 覆盖。

## 3. CLI 兼容

原有命令保持可用，例如：

```bash
python inv.py --help
python inv.py --db ./lab_inventory.db proj-new --code PJ-001 --name "示例项目"
python inv.py --db ./lab_inventory.db proj-status --proj PJ-001
```

## 4. 最小演示流程

1. **创建项目**
   - CLI：`proj-new`
   - 或 UI「项目管理」页创建。
2. **批量导入交易 xlsx（可选）**
   - CLI：`txn-export-xlsx` 导模板，`txn-import-xlsx` 导入。
   - 或 UI「XLSX 导入」页上传。
3. **设置 BOM**
   - CLI：`bom-set`
   - 或 API：`POST /api/projects/{code}/bom`。
4. **预留**
   - CLI：`reserve`
   - 或 UI「项目管理」页填写 `mpn/location/qty`。
5. **消耗/释放**
   - CLI：`consume` / `release`
   - 或 UI 按 `alloc_id` 执行。
6. **添加项目资源并检查**
   - CLI：`project resource add/check`
   - 或 UI「项目资源」页新增、删除、检查。

## 5. 数据一致性与并发

- CLI/API/UI 共享同一个 SQLite 文件，数据实时一致。
- 连接默认启用：`WAL`、`synchronous=NORMAL`、`busy_timeout=30000`、`timeout=30`、`foreign_keys=ON`。
- 当数据库被其他进程长期占用（如 DB Browser）时，API 会返回明确错误：数据库被锁定，请稍后重试。
