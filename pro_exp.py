import sqlite3

# 连接到数据库
db_path = "G:/LabInventory/lab_inventory.db"  # 你自己的数据库路径
conn = sqlite3.connect(db_path)

# 创建新项目
def create_project(project_code, project_name, status='active'):
    conn.execute(
        "INSERT INTO projects (code, name, status, created_at) VALUES (?, ?, ?, datetime('now'))",
        (project_code, project_name, status)
    )
    conn.commit()
    print(f"项目 '{project_name}' 创建成功！")

# 为项目添加物料清单（BOM）
def add_bom_to_project(project_code, mpn, req_qty, priority):
    # 获取 project_id
    project_id = conn.execute("SELECT id FROM projects WHERE code=?", (project_code,)).fetchone()
    if not project_id:
        print(f"项目 '{project_code}' 不存在！")
        return
    project_id = project_id[0]

    # 获取 part_id
    part_id = conn.execute("SELECT id FROM parts WHERE mpn=?", (mpn,)).fetchone()
    if not part_id:
        print(f"物料 '{mpn}' 不存在！")
        return
    part_id = part_id[0]

    # 插入物料到 BOM 表
    conn.execute(
        "INSERT INTO project_bom (project_id, part_id, req_qty, priority, note) VALUES (?, ?, ?, ?, ?)",
        (project_id, part_id, req_qty, priority, "优先级为：{}".format(priority))
    )
    conn.commit()
    print(f"物料 '{mpn}' 添加到项目 '{project_code}' 的 BOM 中！")

# 分配物料并预留库存
def allocate_material_to_project(project_code, mpn, location, alloc_qty):
    # 获取 project_id
    project_id = conn.execute("SELECT id FROM projects WHERE code=?", (project_code,)).fetchone()
    if not project_id:
        print(f"项目 '{project_code}' 不存在！")
        return
    project_id = project_id[0]

    # 获取 part_id
    part_id = conn.execute("SELECT id FROM parts WHERE mpn=?", (mpn,)).fetchone()
    if not part_id:
        print(f"物料 '{mpn}' 不存在！")
        return
    part_id = part_id[0]

    # 插入物料预留记录
    conn.execute(
        "INSERT INTO project_alloc (project_id, part_id, location, alloc_qty, status, updated_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (project_id, part_id, location, alloc_qty, 'reserved')
    )
    conn.commit()
    print(f"物料 '{mpn}' 预留了 {alloc_qty} 个，库位为 '{location}'。")

# 查看项目状态
def check_project_status(project_code):
    project_id = conn.execute("SELECT id FROM projects WHERE code=?", (project_code,)).fetchone()
    if not project_id:
        print(f"项目 '{project_code}' 不存在！")
        return
    project_id = project_id[0]

    # 获取项目的物料分配情况
    allocs = conn.execute(
        "SELECT parts.mpn, project_alloc.alloc_qty, project_alloc.status FROM project_alloc "
        "JOIN parts ON project_alloc.part_id = parts.id WHERE project_alloc.project_id=?",
        (project_id,)
    ).fetchall()

    if not allocs:
        print(f"项目 '{project_code}' 没有物料分配记录！")
        return

    print(f"项目 '{project_code}' 的物料分配情况：")
    for alloc in allocs:
        print(f"物料：{alloc[0]}, 分配数量：{alloc[1]}, 状态：{alloc[2]}")

# 示例：批量管理项目
create_project('PJ-001', '电源系统')  # 创建项目
add_bom_to_project('PJ-001', 'LM1117-3.3', 20, 1)  # 添加物料清单
allocate_material_to_project('PJ-001', 'LM1117-3.3', 'C409-G01-S01-P01', 10)  # 预留物料
check_project_status('PJ-001')  # 查看项目状态

# 提交并关闭数据库连接
conn.commit()
conn.close()