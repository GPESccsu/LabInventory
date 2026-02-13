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
