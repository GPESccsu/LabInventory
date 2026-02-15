# README — Project Resources

## 3 条命令快速起步

```bash
python inv.py --db G:\LabInventory\lab_inventory.db project add --code PJ-001 --name 电源系统
python inv.py --db G:\LabInventory\lab_inventory.db project resource add --code PJ-001 --type hw_pcb --name "PCB工程" --uri "G:\Projects\PJ-001\HW" --is-dir 1 --tags "pcb,kicad"
python inv.py --db G:\LabInventory\lab_inventory.db project resource ls --code PJ-001
```

## 常用命令

- 检查路径有效性：
```bash
python inv.py --db ... project resource check --code PJ-001
```

- 删除资源：
```bash
python inv.py --db ... project resource rm --code PJ-001 --type docs --uri "G:\Projects\PJ-001\Docs"
```

- 项目总览：
```bash
python inv.py --db ... project overview --code PJ-001
```

## 批量导入（XLSX）

导入命令：

```bash
python inv.py --db ... project resource import-xlsx --xlsx G:\LabInventory\project_resources.xlsx --sheet project_resources --header-row 1 --auto-create-project
```

Sheet 列名要求：
- `project_code`（必填）
- `type`（必填）
- `name`（必填）
- `uri`（必填）
- `is_dir`（可选，1/0）
- `tags`（可选）
- `note`（可选）

可参考：`data/reference/project_resources_template.csv`。

## 依赖

XLSX 导入依赖 `openpyxl`：

```bash
python -m pip install openpyxl
```
