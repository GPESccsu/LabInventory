import pandas as pd
import sqlite3
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from pathlib import Path

# 加载 Excel 数据
file_path = 'G:/LabInventory/BoM报价-立创_20260212.xlsx'  # 修改为你的文件路径
excel_data = pd.ExcelFile(file_path)
df = pd.read_excel(excel_data, sheet_name='sheet', header=5)  # header=5 跳过前五行，表头从第六行开始

# 连接数据库
db_path = "G:/LabInventory/lab_inventory.db"  # 你自己的数据库路径
conn = sqlite3.connect(db_path)

def clean_text(s: str) -> str:
    """ 清理字符串 """
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()

def download_pdf(session: requests.Session, pdf_url: str, out_path: Path) -> bool:
    """ 下载 PDF 数据手册 """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with session.get(pdf_url, stream=True, timeout=30) as r:
        r.raise_for_status()
        # 检查返回的内容类型
        ctype = (r.headers.get("Content-Type") or "").lower()
        if ("pdf" not in ctype) and ("octet-stream" not in ctype):
            first = r.raw.read(5)
            if first != b"%PDF-":
                return False
            with open(out_path, "wb") as f:
                f.write(first)
                for chunk in r.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        f.write(chunk)
            return True
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 128):
                if chunk:
                    f.write(chunk)
    return out_path.exists() and out_path.stat().st_size > 1024

def find_datasheet_url(session: requests.Session, base_url: str) -> str:
    """ 从网页中提取数据手册 PDF 链接 """
    # 请求网页内容
    response = session.get(base_url)
    response.raise_for_status()  # 检查请求是否成功
    soup = BeautifulSoup(response.text, 'html.parser')

    # 查找含有“数据手册”或“Datasheet”字样的链接
    for a in soup.find_all("a", href=True):
        txt = clean_text(a.get_text(" ", strip=True))
        href = a["href"]
        full_url = urljoin(base_url, href)  # 处理相对链接
        if re.search(r"(数据手册|Datasheet)", txt, re.I):
            return full_url
    return ""

def get_part_id(conn, mpn):
    """ 获取 parts 表中物料的 ID """
    row = conn.execute("SELECT id FROM parts WHERE mpn=?", (mpn,)).fetchone()
    if row:
        return row[0]
    return None

# 遍历每行 Excel 表格数据
session = requests.Session()
datasheets_dir = Path("G:/LabInventory/datasheets/")  # 数据手册保存目录

for index, row in df.iterrows():
    mpn = row["Manufacturer Part"]
    name = row["商品名称"]
    category = row["目录"]
    package = row["封装"]
    params = row["参数"]
    manufacturer = row["Manufacturer"]
    qty = row["Quantity"]
    note = manufacturer  # 将 Manufacturer 放入 note 字段

    # 获取物料 ID（如果物料已经存在则跳过，否则插入）
    part_id = get_part_id(conn, mpn)
    if not part_id:
        # 插入新的物料记录到 parts 表
        conn.execute(
            "INSERT INTO parts (mpn, name, category, package, params, note, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now','localtime'))",
            (mpn, name, category, package, params, note)
        )
        part_id = get_part_id(conn, mpn)  # 获取新插入的 ID

    # 获取商品链接并下载数据手册
    datasheet_url = row["商品链接"]
    datasheet_local = ""
    if datasheet_url:
        pdf_url = find_datasheet_url(session, datasheet_url)
        if pdf_url:
            datasheet_local = f"{datasheets_dir}/{mpn}.pdf"
            if download_pdf(session, pdf_url, Path(datasheet_local)):
                print(f"下载成功：{pdf_url}")
            else:
                print(f"数据手册下载失败：{pdf_url}")
    
   # 插入库存记录时，确保唯一
    location = "C409-G01-S01-P01"  # 手动填写库位
    conn.execute(
        """
        INSERT OR REPLACE INTO stock (part_id, location, qty, condition, updated_at)
        VALUES (?, ?, ?, ?, datetime('now','localtime'))
        """,
        (part_id, location, qty, "new")
    )


# 提交更改
conn.commit()

# 关闭数据库连接
conn.close()

print("数据处理完成！")