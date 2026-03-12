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

## 本轮补充（Claude 协作优化）
- 新增 `docs/CLAUDE_高效协作计划.md`：
  - 给出“低额度消耗”的协作方法（任务包模板化、先计划后编码、分批次可合并、强制自检闭环）。
  - 提供三类可直接复制的提示词模板（单批次开发、重构方案、低成本巡检）。
  - 给出按 ROI 排序的 Phase 1~4 优化路线，便于后续持续迭代。
- 更新 `README.md`：增加”给 Claude 的高效协作计划”入口，方便快速使用模板。

## Phase 1（可运行性修复）已完成

- **顶层可选依赖改为懒加载**：`requests` 和 `beautifulsoup4` 从顶层 import 移至 `_load_lcsc_deps()` 懒加载函数，仅在 LCSC 功能调用时触发。
- **`python inv.py --help` 在缺 bs4 时不再因为导入失败而崩溃**：所有 LCSC 相关函数的类型注解改为 `Any`（字符串形式），避免运行时名称解析。
- **统一可选依赖错误提示格式**：`_load_openpyxl()` 和新增 `_load_lcsc_deps()` 均采用”poetry add（推荐）/ pip install”双行提示。
- **新增 CLI smoke 测试**：`tests/test_cli_smoke.py`，覆盖主帮助和关键子命令的 `--help` 返回码检查，以及模块 import 不报错验证。
- **更新 README.md**：安装小节增加”可选依赖说明”段落。

## Phase 2（API 契约修复 + 测试闭环）已完成

### 目标
修复 API 层因 schema 缺失导致的 NameError 导入崩溃，补全测试覆盖。

### 问题根因
`backend/app/api.py` 的路由装饰器引用了 9 个未在 `schemas.py` 定义的 Pydantic 模型（`HealthResponse`、`PartListResponse`、`StockListResponse`、`StockInRequest`、`StockOutRequest`、`StockMoveRequest`、`StockAdjustRequest`、`LocationListResponse`、`LedgerResponse`），导致 `import backend.app.api` 立即抛出 `NameError`。此前 API 测试因 fastapi 未安装在测试环境而全部 skip，问题未被发现。

### 改动文件
| 文件 | 变更说明 |
|------|---------|
| `backend/app/schemas.py` | 新增 13 个 Pydantic 模型（`HealthResponse`、`PartRow`、`PartListResponse`、`StockRow`、`StockListResponse`、`StockInRequest`、`StockOutRequest`、`StockMoveRequest`、`StockAdjustRequest`、`LocationRow`、`LocationListResponse`、`LedgerRow`、`LedgerResponse`）|
| `backend/app/api.py` | 补全 import 块，将 9 个新增模型加入导入列表 |
| `tests/test_api_import.py` | 新增 API import smoke 测试（3 项）+ init_db 幂等测试（3 项）|

### 风险评估
- **无破坏性变更**：仅新增 schema 类与测试文件，未修改任何现有逻辑。
- **向后兼容**：所有现有 CLI 子命令、数据库表/视图/触发器均未改动。

### 验收结果
```
poetry run python -c “import backend.app.api”  → OK
poetry run pytest -v                           → 65 passed, 0 failed
python inv.py --help                           → exit 0
```

### 回滚
```bash
git revert <commit-hash>
```

## Phase 3（LLM 集成层 — Mock Provider）已完成

### 目标
为系统增加自然语言交互能力的基础架构。Phase 1 使用纯规则匹配的 Mock Provider，零外部依赖，为后续接入本地/云端 LLM 提供可插拔接口。

### 新增文件
| 文件 | 说明 |
|------|------|
| `backend/app/llm/__init__.py` | 包入口：`get_provider()` 单例工厂 + 公共导出 |
| `backend/app/llm/config.py` | `LLMConfig` 数据类，从 7 个 `LABINV_LLM_*` 环境变量读取配置 |
| `backend/app/llm/base.py` | `BaseLLMProvider` 抽象基类（chat / classify_intent / extract_fields / summarize） |
| `backend/app/llm/mock_provider.py` | `MockProvider`：关键词+正则实现意图分类和字段抽取，不依赖外部服务 |
| `backend/app/llm/intent.py` | `Intent` 枚举 + `ParsedIntent` 数据类 + `parse_intent()` 流水线 |
| `backend/app/llm/summarizer.py` | `summarize_result()` 将查询结果转中文摘要 |

### 修改文件
| 文件 | 变更说明 |
|------|---------|
| `backend/app/schemas.py` | 新增 `LLMChatMessage/Request/Response`、`LLMIntentRequest/Response`、`LLMConfigResponse` |
| `backend/app/api.py` | 新增 3 个路由：`POST /api/llm/chat`、`POST /api/llm/intent`、`GET /api/llm/config` |
| `CLAUDE.md` | 更新目录结构、环境变量表、API 端点表、新增 LLM 架构说明 |
| `README.md` | 新增 LLM / 自然语言接口段落 |

### 设计决策
1. **Provider 抽象**：所有 LLM 调用通过 `BaseLLMProvider` 接口，业务层不直接 import 具体实现。
2. **Mock 优先**：默认 `LABINV_LLM_PROVIDER=mock`，开发/测试零配置即可运行。
3. **意图 + 字段分离**：`classify_intent()` 确定操作类型，`extract_fields()` 按 schema 抽取参数，`ParsedIntent` 聚合结果并报告缺失字段。
4. **延迟 import**：API 路由中 `from backend.app.llm import ...` 放在函数体内，避免 LLM 模块的加载影响不使用 LLM 的场景。

### 验收结果
```
python inv.py --help                              → exit 0
poetry run python -c "import backend.app.api"     → OK
poetry run python -c "from backend.app.llm import get_provider; p = get_provider(); print(p.chat([{'role':'user','content':'帮助'}]))"  → OK
```

## Phase 3.1（Local + Cloud Provider）已完成

### 目标
实现真实 LLM 调用能力，支持本地（Ollama/vLLM）和云端（OpenAI/Anthropic/DeepSeek）模型。

### 新增文件
| 文件 | 说明 |
|------|------|
| `backend/app/llm/local_provider.py` | `LocalProvider`：通过 OpenAI 兼容 API 调用本地模型（Ollama/vLLM/LocalAI） |
| `backend/app/llm/cloud_provider.py` | `CloudProvider`：调用云端 API（OpenAI/Anthropic/DeepSeek），支持 `api_type` 切换 |

### 设计决策
1. **Local/Cloud 共用 `chat_json()`**：继承自 `BaseLLMProvider` 的结构化 JSON 输出方法，意图分类和字段抽取均通过此接口实现。
2. **Anthropic 特殊处理**：Messages API 需要分离 system 消息、使用 `x-api-key` 头、解析 content blocks 数组。
3. **api_type 路由**：CloudProvider 通过 `LABINV_LLM_API_TYPE` 区分 `openai` / `anthropic` / `deepseek`，各有默认 base URL。

## Phase 3.2（NL 查询 + 草稿确认工作流）已完成

### 目标
实现自然语言驱动的数据库查询和库存操作，遵循"LLM 不编造数据、写操作需确认"原则。

### 新增文件
| 文件 | 说明 |
|------|------|
| `backend/app/llm/query_executor.py` | `execute_query()`：将 ParsedIntent 转为 InventoryService 真实查询 |
| `backend/app/llm/draft_builder.py` | `build_draft()`：将 ParsedIntent 转为库存操作草稿（不执行） |
| `backend/app/llm_service.py` | `LLMService` 业务门面：聚合 parse/query/draft/execute/resource_qa |

### 新增 API 端点
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/llm/ping` | 检测 LLM provider 连通性 |
| POST | `/api/llm/parse` | 意图解析 + 字段抽取 + 摘要（一次调用完成） |
| POST | `/api/llm/query` | 自然语言 → 真实数据库查询 → 中文结果 |
| POST | `/api/llm/draft-stock-op` | 自然语言 → 库存操作草稿（不执行） |
| POST | `/api/llm/execute-draft` | 确认并执行草稿 |

### 设计决策
1. **查询与写操作分离**：查询类意图（query_stock/query_parts/query_ledger/project_status）直接执行返回数据；写操作（stock_in/out/move/adjust）只生成草稿，需用户确认后再执行。
2. **LLMService 门面模式**：业务层只 import `llm_service`，不直接触碰 provider/config/intent。
3. **execute_draft 复用现有逻辑**：通过 InventoryService 执行，不绕过任何业务规则和数据库 trigger。

## Phase 3.3（项目资源 Q&A）已完成

### 目标
基于项目关联的资源信息（文件路径、URL、标签等），回答用户关于项目资源的问题。

### 新增文件
| 文件 | 说明 |
|------|------|
| `backend/app/llm/resource_qa.py` | `build_resource_context()` + `ask_resource_qa()`：构建资源上下文并通过 LLM 回答 |

### 新增 API 端点
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects/{code}/resources/qa` | 项目资源问答 |

---

## 后续优化方向

### P0（近期可做）
- **Streamlit LLM 聊天面板**：前端对接 `/api/llm/chat` 和 `/api/llm/query`，提供自然语言交互 UI。
- **测试覆盖扩展**：为 LLM 服务层、query_executor、draft_builder 补充单元测试。

### P1（中期建议）
- **批量操作优化**：BOM 批量设置、批量入库的性能优化（事务合并）。
- **操作审计日志**：记录谁在什么时候通过什么方式（CLI/API/NL）执行了什么操作。
- **库存报表导出**：按项目/库位/类别生成汇总报表（PDF/XLSX）。

### P2（长期方向）
- **多用户权限**：基于角色的操作权限控制。
- **供应商管理**：BOM 成本追踪、供应商信息关联。
- **条码/二维码**：库位标签打印与扫码操作。
