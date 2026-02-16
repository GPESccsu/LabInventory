# PLAN.md — Web 化改造落地（本次执行）

## 目标
在保持 `inv.py` CLI 兼容的前提下，新增 FastAPI + Streamlit，并抽离共享业务层。

## 本次已完成
- 新增 `backend/app/db.py`
  - 统一 `connect()`：`timeout=30`、`check_same_thread=False`。
  - PRAGMA：`journal_mode=WAL`、`synchronous=NORMAL`、`busy_timeout=30000`、`foreign_keys=ON`。
  - `init_db()` 复用原 `inv.py` 幂等初始化。
- 新增 `backend/app/core.py`
  - 对项目/BOM/预留/释放/消耗/资源/XLSX 导入提供统一函数接口。
  - API 与后续扩展均通过 core 调用，避免逻辑分叉。
  - 增加 `database is locked` 的统一错误归一化。
- 新增 `backend/app/schemas.py`
  - 集中定义 API 请求/响应模型（Pydantic）。
- 新增 `backend/app/api.py`
  - 完成项目、BOM、预留/释放/消耗、资源管理、交易/资源 XLSX 导入 API。
- 新增 `frontend/streamlit_app.py`
  - 中文界面，覆盖项目列表与创建、项目状态、预留、释放/消耗、资源管理、XLSX 导入。
  - UI 全部通过 HTTP 调用 API，不直接访问数据库。
- 更新 `pyproject.toml`
  - 使用 Poetry 管理依赖，包含 FastAPI/Streamlit/Pydantic/Uvicorn 等。
- 更新 `README.md`
  - 中文安装、启动、最小流程、并发说明。
- 兼容性处理
  - `backend/app/inv.py` 为 CLI 主实现；根目录 `inv.py` 与 `app/` 保持兼容转发，保证现有命令入口与行为不变。

## 验收关注点
- `python inv.py --help` 正常。
- API 与 UI 指向同一数据库文件时，数据读写一致。
- 写入冲突时返回清晰的数据库锁定错误。
