import argparse
import csv
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ---------------------------
# 基础工具
# ---------------------------
def clean_text(s: str) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def safe_filename(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", "_", name)
    return name[:180] if len(name) > 180 else name


def normalize_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


def now_local_sql() -> str:
    return "datetime('now','localtime')"


# ---------------------------
# 数据库初始化（幂等）
# ---------------------------
DDL = r"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS parts (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  mpn           TEXT NOT NULL,
  name          TEXT NOT NULL,
  category      TEXT NOT NULL,
  package       TEXT,
  params        TEXT,
  unit          TEXT NOT NULL DEFAULT 'pcs',
  url           TEXT,
  datasheet     TEXT,
  note          TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_parts_mpn ON parts(mpn);
CREATE INDEX IF NOT EXISTS idx_parts_search ON parts(name, category);

CREATE TABLE IF NOT EXISTS stock (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  part_id       INTEGER NOT NULL,
  location      TEXT NOT NULL,
  qty           INTEGER NOT NULL DEFAULT 0,
  condition     TEXT NOT NULL DEFAULT 'new',
  updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  note          TEXT,
  FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_stock_part ON stock(part_id);
CREATE INDEX IF NOT EXISTS idx_stock_loc  ON stock(location);

CREATE TABLE IF NOT EXISTS locations (
  location   TEXT PRIMARY KEY,
  note       TEXT
);

CREATE TABLE IF NOT EXISTS projects (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  code        TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  owner       TEXT,
  status      TEXT NOT NULL DEFAULT 'active',
  note        TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS project_bom (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL,
  part_id     INTEGER NOT NULL,
  req_qty     INTEGER NOT NULL DEFAULT 1,
  priority    INTEGER NOT NULL DEFAULT 2,
  note        TEXT,
  UNIQUE(project_id, part_id),
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_bom_project ON project_bom(project_id);
CREATE INDEX IF NOT EXISTS idx_bom_part    ON project_bom(part_id);

CREATE TABLE IF NOT EXISTS project_alloc (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL,
  part_id     INTEGER NOT NULL,
  location    TEXT,
  alloc_qty   INTEGER NOT NULL DEFAULT 0,
  status      TEXT NOT NULL DEFAULT 'reserved',
  note        TEXT,
  updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_alloc_project ON project_alloc(project_id);
CREATE INDEX IF NOT EXISTS idx_alloc_part    ON project_alloc(part_id);
CREATE INDEX IF NOT EXISTS idx_alloc_loc     ON project_alloc(location);

-- 位置合法性（location 不为空时必须存在）
CREATE TRIGGER IF NOT EXISTS trg_alloc_location_check
BEFORE INSERT ON project_alloc
WHEN NEW.location IS NOT NULL AND NEW.location <> ''
BEGIN
  SELECT
    CASE
      WHEN (SELECT COUNT(1) FROM locations WHERE location = NEW.location) = 0
      THEN RAISE(ABORT, 'location 不存在于 locations 表')
    END;
END;

CREATE TRIGGER IF NOT EXISTS trg_alloc_location_check_u
BEFORE UPDATE OF location ON project_alloc
WHEN NEW.location IS NOT NULL AND NEW.location <> ''
BEGIN
  SELECT
    CASE
      WHEN (SELECT COUNT(1) FROM locations WHERE location = NEW.location) = 0
      THEN RAISE(ABORT, 'location 不存在于 locations 表')
    END;
END;

-- 强约束：禁止超预留（全局 + 库位）
DROP TRIGGER IF EXISTS trg_alloc_no_overreserve_ins;
DROP TRIGGER IF EXISTS trg_alloc_no_overreserve_upd;

CREATE TRIGGER trg_alloc_no_overreserve_ins
BEFORE INSERT ON project_alloc
WHEN NEW.alloc_qty > 0
 AND NEW.status IN ('reserved','consumed')
BEGIN
  SELECT
    CASE
      WHEN (
        IFNULL((SELECT SUM(qty) FROM stock WHERE part_id = NEW.part_id), 0)
        -
        IFNULL((SELECT SUM(alloc_qty) FROM project_alloc
                WHERE part_id = NEW.part_id
                  AND status IN ('reserved','consumed')
                  AND alloc_qty > 0), 0)
      ) < NEW.alloc_qty
      THEN RAISE(ABORT, '超预留：全局可用库存不足')
    END;

  SELECT
    CASE
      WHEN (NEW.location IS NOT NULL AND NEW.location <> '')
       AND (
        IFNULL((SELECT SUM(qty) FROM stock
                WHERE part_id = NEW.part_id AND location = NEW.location), 0)
        -
        IFNULL((SELECT SUM(alloc_qty) FROM project_alloc
                WHERE part_id = NEW.part_id
                  AND location = NEW.location
                  AND status IN ('reserved','consumed')
                  AND alloc_qty > 0), 0)
      ) < NEW.alloc_qty
      THEN RAISE(ABORT, '超预留：该库位可用库存不足')
    END;
END;

CREATE TRIGGER trg_alloc_no_overreserve_upd
BEFORE UPDATE OF part_id, location, alloc_qty, status ON project_alloc
WHEN NEW.alloc_qty > 0
 AND NEW.status IN ('reserved','consumed')
BEGIN
  SELECT
    CASE
      WHEN (
        IFNULL((SELECT SUM(qty) FROM stock WHERE part_id = NEW.part_id), 0)
        -
        IFNULL((SELECT SUM(alloc_qty) FROM project_alloc
                WHERE part_id = NEW.part_id
                  AND status IN ('reserved','consumed')
                  AND alloc_qty > 0
                  AND id <> OLD.id), 0)
      ) < NEW.alloc_qty
      THEN RAISE(ABORT, '超预留：全局可用库存不足（更新被阻止）')
    END;

  SELECT
    CASE
      WHEN (NEW.location IS NOT NULL AND NEW.location <> '')
       AND (
        IFNULL((SELECT SUM(qty) FROM stock
                WHERE part_id = NEW.part_id AND location = NEW.location), 0)
        -
        IFNULL((SELECT SUM(alloc_qty) FROM project_alloc
                WHERE part_id = NEW.part_id
                  AND location = NEW.location
                  AND status IN ('reserved','consumed')
                  AND alloc_qty > 0
                  AND id <> OLD.id), 0)
      ) < NEW.alloc_qty
      THEN RAISE(ABORT, '超预留：该库位可用库存不足（更新被阻止）')
    END;
END;

-- 视图：项目物料状态
CREATE VIEW IF NOT EXISTS v_project_material_status AS
WITH
stock_sum AS (
  SELECT part_id, SUM(qty) AS total_stock
  FROM stock
  GROUP BY part_id
),
alloc_sum_all AS (
  SELECT part_id, SUM(CASE WHEN status IN ('reserved','consumed') AND alloc_qty>0 THEN alloc_qty ELSE 0 END) AS reserved_qty
  FROM project_alloc
  GROUP BY part_id
),
alloc_sum_proj AS (
  SELECT project_id, part_id, SUM(CASE WHEN status IN ('reserved','consumed') AND alloc_qty>0 THEN alloc_qty ELSE 0 END) AS reserved_for_project
  FROM project_alloc
  GROUP BY project_id, part_id
)
SELECT
  pr.code AS project_code,
  pr.name AS project_name,
  p.category,
  p.mpn,
  p.name AS part_desc,
  p.package,
  p.params,
  b.req_qty,
  IFNULL(ss.total_stock, 0) AS total_stock,
  IFNULL(aa.reserved_qty, 0) AS reserved_qty_all_projects,
  (IFNULL(ss.total_stock, 0) - IFNULL(aa.reserved_qty, 0)) AS available_stock,
  IFNULL(ap.reserved_for_project, 0) AS reserved_for_project,
  (b.req_qty - IFNULL(ap.reserved_for_project, 0)) AS remaining_to_reserve,
  CASE
    WHEN (IFNULL(ss.total_stock, 0) - IFNULL(aa.reserved_qty, 0)) >= (b.req_qty - IFNULL(ap.reserved_for_project, 0))
      THEN 0
    ELSE (b.req_qty - IFNULL(ap.reserved_for_project, 0)) - (IFNULL(ss.total_stock, 0) - IFNULL(aa.reserved_qty, 0))
  END AS shortage_if_reserve_now
FROM project_bom b
JOIN projects pr ON pr.id = b.project_id
JOIN parts p     ON p.id  = b.part_id
LEFT JOIN stock_sum ss      ON ss.part_id = p.id
LEFT JOIN alloc_sum_all aa  ON aa.part_id = p.id
LEFT JOIN alloc_sum_proj ap ON ap.project_id = pr.id AND ap.part_id = p.id;

-- 视图：预留明细
CREATE VIEW IF NOT EXISTS v_project_alloc_detail AS
SELECT
  pr.code AS project_code,
  pr.name AS project_name,
  p.mpn,
  p.name AS part_desc,
  a.location,
  a.alloc_qty,
  a.status,
  a.updated_at,
  a.note
FROM project_alloc a
JOIN projects pr ON pr.id = a.project_id
JOIN parts p     ON p.id  = a.part_id;
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(conn: sqlite3.Connection):
    conn.executescript(DDL)
    conn.commit()


# ---------------------------
# 立创抓取 + 数据手册下载
# ---------------------------
def find_value_by_label(soup: BeautifulSoup, label: str) -> str:
    text = soup.get_text("\n", strip=True)
    m = re.search(rf"{re.escape(label)}\s*\n([^\n]+)", text)
    if m:
        return clean_text(m.group(1))
    m = re.search(rf"{re.escape(label)}\s*[:：]?\s*([^\n]+)", text)
    if m:
        return clean_text(m.group(1))
    return ""


def parse_params_table(soup: BeautifulSoup) -> dict:
    text = soup.get_text("\n", strip=True)
    if "商品参数" not in text:
        return {}
    tail = text.split("商品参数", 1)[1]
    lines = [clean_text(x) for x in tail.split("\n") if clean_text(x)]

    start_idx = None
    for i in range(len(lines) - 1):
        if lines[i] == "属性" and lines[i + 1] == "参数值":
            start_idx = i + 2
            break
    if start_idx is None:
        return {}

    end_signals = {"相似推荐", "其他推荐", "客服", "反馈", "收起", "置顶"}
    pairs = {}
    i = start_idx
    while i + 1 < len(lines):
        if lines[i] in end_signals:
            break
        key = lines[i]
        val = lines[i + 1]
        if key and val and key not in {"属性", "参数值"} and key not in pairs:
            pairs[key] = val
        i += 2
    return pairs


def find_datasheet_url(soup: BeautifulSoup, base_url: str) -> str:
    candidates = []

    for a in soup.find_all("a", href=True):
        txt = clean_text(a.get_text(" ", strip=True))
        href = a["href"]
        full = urljoin(base_url, href)
        if re.search(r"(数据手册|Datasheet)", txt, re.I):
            candidates.append(full)

    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base_url, href)
        if ".pdf" in full.lower():
            candidates.append(full)

    raw = str(soup)
    for m in re.finditer(r"https?://[^\s\"']+\.pdf", raw, flags=re.I):
        candidates.append(m.group(0))

    seen, uniq = set(), []
    for u in candidates:
        u = u.strip()
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)

    for u in uniq:
        if u.lower().endswith(".pdf"):
            return u
    for u in uniq:
        if ".pdf" in u.lower():
            return u
    return ""


def download_pdf(session: requests.Session, pdf_url: str, out_path: Path) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with session.get(pdf_url, stream=True, timeout=30) as r:
        r.raise_for_status()
        ctype = (r.headers.get("Content-Type") or "").lower()

        # content-type 异常时检查 PDF 头
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


@dataclass
class LcscItem:
    mpn: str
    desc: str
    category: str
    package: str
    brand: str
    lcsc_code: str
    params_text: str
    page_url: str
    datasheet_local: str
    note: str


def lcsc_fetch_and_parse(url: str, datasheets_dir: Path) -> LcscItem:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9",
    })

    page_url = normalize_url(url)
    html = session.get(page_url, timeout=20)
    html.raise_for_status()
    html.encoding = html.apparent_encoding or "utf-8"

    soup = BeautifulSoup(html.text, "lxml")

    mpn = find_value_by_label(soup, "商品型号")
    if not mpn:
        t = soup.get_text("\n", strip=True)
        m = re.search(r"商品型号\s*[:：]?\s*([A-Za-z0-9\-_.]+)", t)
        mpn = m.group(1) if m else ""
    if not mpn:
        raise RuntimeError("解析失败：未找到商品型号")

    desc = find_value_by_label(soup, "描述") or mpn
    category = find_value_by_label(soup, "商品目录") or "未分类"
    package = find_value_by_label(soup, "商品封装")
    brand = find_value_by_label(soup, "品牌名称")
    lcsc_code = find_value_by_label(soup, "商品编号")

    params = parse_params_table(soup)
    params_text = "; ".join([f"{k}={v}" for k, v in params.items()]) if params else ""

    # datasheet：默认商品页，下载成功则本地路径
    datasheet_value = page_url
    pdf_url = find_datasheet_url(soup, page_url)

    note_parts = []
    if brand:
        note_parts.append(f"品牌={brand}")
    if lcsc_code:
        note_parts.append(f"LCSC={lcsc_code}")
    note_parts.append(f"URL={page_url}")

    datasheet_local = ""
    if pdf_url:
        base = safe_filename(mpn)
        if lcsc_code:
            base += f"__{safe_filename(lcsc_code)}"
        out_pdf = datasheets_dir / f"{base}.pdf"
        try:
            if download_pdf(session, pdf_url, out_pdf):
                datasheet_value = str(out_pdf)
                datasheet_local = str(out_pdf)
                note_parts.append(f"DatasheetPDF={pdf_url}")
            else:
                note_parts.append(f"DatasheetPDF下载失败={pdf_url}")
        except Exception as e:
            note_parts.append(f"DatasheetPDF异常={pdf_url} ({type(e).__name__})")
    else:
        note_parts.append("DatasheetPDF未找到")

    note = " | ".join(note_parts)

    return LcscItem(
        mpn=mpn,
        desc=desc,
        category=category,
        package=package,
        brand=brand,
        lcsc_code=lcsc_code,
        params_text=params_text,
        page_url=page_url,
        datasheet_local=datasheet_local,
        note=note,
    )


# ---------------------------
# DB 操作函数（全部通过脚本）
# ---------------------------
def get_project_id(conn, code: str) -> int:
    r = conn.execute("SELECT id FROM projects WHERE code=?", (code,)).fetchone()
    if not r:
        raise RuntimeError(f"项目不存在：{code}")
    return int(r["id"])


def get_part_id_by_mpn(conn, mpn: str) -> int:
    r = conn.execute("SELECT id FROM parts WHERE mpn=?", (mpn,)).fetchone()
    if not r:
        raise RuntimeError(f"物料不存在：{mpn}")
    return int(r["id"])


def upsert_part(conn, mpn: str, name: str, category: str, package: str, params: str, datasheet: str, note: str) -> int:
    row = conn.execute("SELECT id FROM parts WHERE mpn=?", (mpn,)).fetchone()
    if row:
        pid = int(row["id"])
        conn.execute(
            """
            UPDATE parts
            SET name=COALESCE(NULLIF(?,''), name),
                category=COALESCE(NULLIF(?,''), category),
                package=COALESCE(NULLIF(?,''), package),
                params=COALESCE(NULLIF(?,''), params),
                datasheet=COALESCE(NULLIF(?,''), datasheet),
                note=COALESCE(NULLIF(?,''), note)
            WHERE id=?
            """,
            (name, category, package, params, datasheet, note, pid),
        )
        return pid
    cur = conn.execute(
        "INSERT INTO parts (mpn, name, category, package, params, datasheet, note) VALUES (?,?,?,?,?,?,?)",
        (mpn, name, category, package, params, datasheet, note),
    )
    return int(cur.lastrowid)


def add_stock(conn, mpn: str, location: str, qty: int, condition: str = "new", note: str = ""):
    # location 合法性
    if conn.execute("SELECT 1 FROM locations WHERE location=?", (location,)).fetchone() is None:
        raise RuntimeError(f"库位不存在（locations 表里没有）：{location}")
    part_id = get_part_id_by_mpn(conn, mpn)
    row = conn.execute("SELECT id, qty FROM stock WHERE part_id=? AND location=?", (part_id, location)).fetchone()
    if row:
        conn.execute(
            "UPDATE stock SET qty=?, updated_at=datetime('now','localtime'), condition=?, note=? WHERE id=?",
            (int(row["qty"]) + qty, condition, note, int(row["id"])),
        )
    else:
        conn.execute(
            "INSERT INTO stock (part_id, location, qty, condition, note) VALUES (?,?,?,?,?)",
            (part_id, location, qty, condition, note),
        )


def create_project(conn, code: str, name: str, owner: str = "", note: str = ""):
    conn.execute(
        "INSERT INTO projects (code, name, owner, note) VALUES (?,?,?,?)",
        (code, name, owner or None, note or None),
    )


def set_bom(conn, project_code: str, mpn: str, req_qty: int, priority: int = 2, note: str = ""):
    pid = get_project_id(conn, project_code)
    part_id = get_part_id_by_mpn(conn, mpn)
    # upsert bom
    row = conn.execute("SELECT id FROM project_bom WHERE project_id=? AND part_id=?", (pid, part_id)).fetchone()
    if row:
        conn.execute(
            "UPDATE project_bom SET req_qty=?, priority=?, note=? WHERE id=?",
            (req_qty, priority, note, int(row["id"])),
        )
    else:
        conn.execute(
            "INSERT INTO project_bom (project_id, part_id, req_qty, priority, note) VALUES (?,?,?,?,?)",
            (pid, part_id, req_qty, priority, note),
        )


def reserve_loc(conn, project_code: str, mpn: str, location: str, qty: int, note: str = "") -> int:
    if qty <= 0:
        raise RuntimeError("预留数量必须为正整数")
    # location 合法性（触发器也会检查，这里提前报错更友好）
    if conn.execute("SELECT 1 FROM locations WHERE location=?", (location,)).fetchone() is None:
        raise RuntimeError(f"库位不存在：{location}")

    pid = get_project_id(conn, project_code)
    part_id = get_part_id_by_mpn(conn, mpn)

    cur = conn.execute(
        "INSERT INTO project_alloc (project_id, part_id, location, alloc_qty, status, note, updated_at) VALUES (?,?,?,?, 'reserved', ?, datetime('now','localtime'))",
        (pid, part_id, location, qty, note),
    )
    return int(cur.lastrowid)


def release_alloc(conn, alloc_id: int, note_append: str = "释放"):
    row = conn.execute("SELECT status FROM project_alloc WHERE id=?", (alloc_id,)).fetchone()
    if not row:
        raise RuntimeError(f"alloc_id 不存在：{alloc_id}")
    conn.execute(
        "UPDATE project_alloc SET status='released', updated_at=datetime('now','localtime'), note=COALESCE(note,'') || ? WHERE id=?",
        (f" | {note_append}", alloc_id),
    )


def consume_alloc(conn, alloc_id: int, note_append: str = "已消耗"):
    """
    消耗 = 将 alloc 标记为 consumed + 扣减 stock（同一 part + location）
    强约束已保证 alloc 不会超预留，但 stock 扣减还需要确保该库位 stock 行存在且足够。
    """
    a = conn.execute("SELECT part_id, location, alloc_qty, status FROM project_alloc WHERE id=?", (alloc_id,)).fetchone()
    if not a:
        raise RuntimeError(f"alloc_id 不存在：{alloc_id}")
    if a["status"] != "reserved":
        raise RuntimeError(f"只有 reserved 状态才能消耗，当前={a['status']}")

    part_id = int(a["part_id"])
    location = clean_text(a["location"])
    qty = int(a["alloc_qty"])
    if not location:
        raise RuntimeError("带库位预留要求 location 非空，当前记录没有 location")

    s = conn.execute("SELECT id, qty FROM stock WHERE part_id=? AND location=?", (part_id, location)).fetchone()
    if not s:
        raise RuntimeError(f"stock 中找不到该库位记录：part_id={part_id}, location={location}")
    if int(s["qty"]) < qty:
        raise RuntimeError(f"扣减失败：库位库存不足（stock={int(s['qty'])} < consume={qty}）")

    # 事务：要么都成功要么都失败
    conn.execute("BEGIN;")
    try:
        conn.execute(
            "UPDATE stock SET qty=qty-?, updated_at=datetime('now','localtime') WHERE id=?",
            (qty, int(s["id"])),
        )
        conn.execute(
            "UPDATE project_alloc SET status='consumed', updated_at=datetime('now','localtime'), note=COALESCE(note,'') || ? WHERE id=?",
            (f" | {note_append}", alloc_id),
        )
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise


def show_project_status(conn, project_code: str):
    rows = conn.execute(
        "SELECT * FROM v_project_material_status WHERE project_code=? ORDER BY category, mpn",
        (project_code,),
    ).fetchall()
    if not rows:
        print("没有记录（项目不存在或未建 BOM）")
        return
    # 简洁输出
    headers = ["mpn", "part_desc", "req_qty", "total_stock", "reserved_qty_all_projects",
               "available_stock", "reserved_for_project", "remaining_to_reserve", "shortage_if_reserve_now", "package"]
    print("\t".join(headers))
    for r in rows:
        print("\t".join(str(r[h]) for h in headers))


def show_alloc_detail(conn, project_code: str):
    rows = conn.execute(
        "SELECT * FROM v_project_alloc_detail WHERE project_code=? ORDER BY updated_at DESC",
        (project_code,),
    ).fetchall()
    if not rows:
        print("没有预留记录")
        return
    headers = ["updated_at", "mpn", "location", "alloc_qty", "status", "note"]
    print("\t".join(headers))
    for r in rows:
        print("\t".join(str(r[h]) for h in headers))

def init_locations(conn, room: str, cabinets: list, positions_per_shelf: int = 10, overwrite_note: bool = False):
    """
    cabinets: list of dicts, e.g.
      [{"code":"G01","shelves":3,"note":"三层柜 30x80x35"},
       {"code":"G02","shelves":1,"note":"一层柜 40x100x40"}]
    """
    total = 0
    for cab in cabinets:
        g = cab["code"]
        shelves = int(cab["shelves"])
        cab_note = cab.get("note", "")
        for s in range(1, shelves + 1):
            for p in range(1, positions_per_shelf + 1):
                loc = f"{room}-{g}-S{s:02d}-P{p:02d}"
                note = f"{room} {g} 第{s}层 位{p:02d}"
                if cab_note:
                    note = note + f" | {cab_note}"
                # 插入或忽略（避免重复）
                conn.execute(
                    "INSERT OR IGNORE INTO locations (location, note) VALUES (?, ?)",
                    (loc, note),
                )
                if overwrite_note:
                    conn.execute(
                        "UPDATE locations SET note=? WHERE location=?",
                        (note, loc),
                    )
                total += 1
    return total


def _pick_first(d: dict, names: list[str], default=""):
    for n in names:
        if n in d and clean_text(d.get(n)):
            return clean_text(d.get(n))
    return default


def _to_float(v, default=0.0) -> float:
    s = clean_text(v)
    if not s:
        return default
    s = s.replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else default


def _to_int(v, default=0) -> int:
    return int(round(_to_float(v, float(default))))


def _load_lcsc_rows(path: Path) -> list[dict]:
    ext = path.suffix.lower()
    if ext == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    if ext in {".xlsx", ".xls"}:
        try:
            import pandas as pd
        except Exception as e:
            raise RuntimeError("读取 Excel 需要 pandas，请先安装 pandas") from e
        df = pd.read_excel(path)
        return [
            {str(k): ("" if pd.isna(v) else str(v)) for k, v in row.items()}
            for row in df.to_dict(orient="records")
        ]
    raise RuntimeError("立创导出文件仅支持 .csv/.xlsx/.xls")


def export_project_forms(
    conn,
    project_code: str,
    outbound_csv: Path,
    inbound_csv: Path,
    lcsc_file: Path | None = None,
    inbound_location: str = "",
    apply_inbound: bool = False,
):
    # 出库单：基于项目 BOM，数量留空给人工填写
    out_rows = conn.execute(
        """
        SELECT p.name AS name, p.package AS package, p.unit AS unit
        FROM project_bom b
        JOIN projects pr ON pr.id = b.project_id
        JOIN parts p ON p.id = b.part_id
        WHERE pr.code = ?
        ORDER BY p.category, p.mpn
        """,
        (project_code,),
    ).fetchall()
    if not out_rows:
        raise RuntimeError(f"项目未找到或 BOM 为空：{project_code}")

    now_str = datetime.now().strftime("%Y-%m-%d")
    outbound_csv.parent.mkdir(parents=True, exist_ok=True)
    with outbound_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["序号", "时间", "名称", "型号规格", "单位", "数量", "单价(元)", "总额(元)", "领用人", "领用时间", "用途", "项目"])
        for i, r in enumerate(out_rows, start=1):
            w.writerow([i, now_str, r["name"], r["package"] or "", r["unit"] or "pcs", "", "", "", "", "", "", project_code])

    # 入库单：优先使用立创导出数据；若未提供则回退为项目 BOM 需求数量
    inbound_records = []
    if lcsc_file:
        raw_rows = _load_lcsc_rows(lcsc_file)
        for row in raw_rows:
            mpn = _pick_first(row, ["型号", "Manufacturer Part", "MPN", "mpn"])
            name = _pick_first(row, ["商品名称", "Name", "名称"], default=mpn)
            if not (mpn or name):
                continue
            qty = _to_int(_pick_first(row, ["购买数量", "数量", "Quantity", "qty"], default="0"), 0)
            price = _to_float(_pick_first(row, ["单价(RMB)", "单价", "price"], default="0"), 0.0)
            total = _to_float(_pick_first(row, ["小计(RMB)", "总价", "total"], default="0"), 0.0)
            if total <= 0 and qty > 0 and price > 0:
                total = qty * price
            inbound_records.append({
                "mpn": mpn,
                "name": name,
                "package": _pick_first(row, ["封装", "Footprint 封装", "Footprint", "package"]),
                "unit": "pcs",
                "qty": qty,
                "price": price,
                "total": total,
            })
    else:
        rows = conn.execute(
            """
            SELECT p.mpn, p.name, p.package, p.unit, b.req_qty
            FROM project_bom b
            JOIN projects pr ON pr.id = b.project_id
            JOIN parts p ON p.id = b.part_id
            WHERE pr.code = ?
            ORDER BY p.category, p.mpn
            """,
            (project_code,),
        ).fetchall()
        inbound_records = [
            {"mpn": r["mpn"], "name": r["name"], "package": r["package"] or "", "unit": r["unit"] or "pcs", "qty": int(r["req_qty"]), "price": 0.0, "total": 0.0}
            for r in rows
        ]

    inbound_csv.parent.mkdir(parents=True, exist_ok=True)
    with inbound_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["序号", "时间", "名称", "型号规格", "单位", "数量", "单价(元)", "总额(元)", "项目"])
        for i, r in enumerate(inbound_records, start=1):
            w.writerow([i, now_str, r["name"], r["package"] or r["mpn"], r["unit"], r["qty"], f"{r['price']:.4f}" if r["price"] else "", f"{r['total']:.4f}" if r["total"] else "", project_code])

    if apply_inbound:
        if not inbound_location:
            raise RuntimeError("执行入库写库时必须提供 --inbound-loc")
        for r in inbound_records:
            if r["qty"] <= 0:
                continue
            row = conn.execute("SELECT id FROM parts WHERE mpn=?", (r["mpn"],)).fetchone()
            if row is None:
                upsert_part(
                    conn,
                    mpn=r["mpn"],
                    name=r["name"] or r["mpn"],
                    category="立创导入",
                    package=r["package"],
                    params="",
                    datasheet="",
                    note=f"project={project_code}",
                )
            add_stock(conn, r["mpn"], inbound_location, int(r["qty"]), "new", f"project={project_code} lcsc入库")
# ---------------------------
# CLI
# ---------------------------
def main():
    ap = argparse.ArgumentParser(description="实验室元器件/设备库存 + 项目管理（SQLite）")
    ap.add_argument("--db", required=True, help=r"数据库路径，例如 G:\LabInventory\lab_inventory.db")

    sub = ap.add_subparsers(dest="cmd", required=True)
    
    # init locations
    p = sub.add_parser("init-locations", help="初始化库位编码到 locations 表（默认按柜子/层/位生成）")
    p.add_argument("--room", default="C409", help="房间号，例如 C409")
    p.add_argument("--g01-shelves", type=int, default=3, help="G01 层数（默认3）")
    p.add_argument("--g02-shelves", type=int, default=1, help="G02 层数（默认1）")
    p.add_argument("--positions", type=int, default=10, help="每层位置数（默认10：P01~P10）")
    p.add_argument("--overwrite-note", action="store_true", help="覆盖更新 locations.note（默认不覆盖）")

    # lcsc import
    p = sub.add_parser("lcsc", help="从立创商品链接导入物料并自动下载数据手册")
    p.add_argument("--url", required=True, help="立创商品链接")
    p.add_argument("--datasheets-dir", default="", help=r"数据手册保存目录（默认=数据库同级 datasheets）")

    # stock in
    p = sub.add_parser("stock-in", help="入库（按库位增加库存）")
    p.add_argument("--mpn", required=True)
    p.add_argument("--loc", required=True)
    p.add_argument("--qty", type=int, required=True)
    p.add_argument("--condition", default="new")
    p.add_argument("--note", default="")

    # project create
    p = sub.add_parser("proj-new", help="创建项目")
    p.add_argument("--code", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--owner", default="")
    p.add_argument("--note", default="")

    # bom set
    p = sub.add_parser("bom-set", help="设置/更新项目BOM需求")
    p.add_argument("--proj", required=True, help="项目 code，例如 PJ-001")
    p.add_argument("--mpn", required=True)
    p.add_argument("--req", type=int, required=True, help="需求数量")
    p.add_argument("--priority", type=int, default=2)
    p.add_argument("--note", default="")

    # reserve
    p = sub.add_parser("reserve", help="带库位预留（强约束：禁止超预留）")
    p.add_argument("--proj", required=True)
    p.add_argument("--mpn", required=True)
    p.add_argument("--loc", required=True)
    p.add_argument("--qty", type=int, required=True)
    p.add_argument("--note", default="")

    # release
    p = sub.add_parser("release", help="释放预留（按 alloc_id）")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--note", default="释放")

    # consume
    p = sub.add_parser("consume", help="消耗预留（按 alloc_id），同时扣减 stock")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--note", default="已消耗")

    # show status
    p = sub.add_parser("proj-status", help="查看项目备料状态（BOM+库存+预留）")
    p.add_argument("--proj", required=True)

    # show alloc
    p = sub.add_parser("proj-alloc", help="查看项目预留明细（带库位）")
    p.add_argument("--proj", required=True)

    # project forms
    p = sub.add_parser("proj-forms", help="按项目生成出库/入库单 CSV；出库数量留空人工填写")
    p.add_argument("--proj", required=True, help="项目 code")
    p.add_argument("--outbound-csv", required=True, help="导出的出库单 CSV 路径")
    p.add_argument("--inbound-csv", required=True, help="导出的入库单 CSV 路径")
    p.add_argument("--lcsc-file", default="", help="立创导出文件（csv/xlsx/xls），用于填充入库单")
    p.add_argument("--apply-inbound", action="store_true", help="将入库单数量写入库存")
    p.add_argument("--inbound-loc", default="", help="执行 --apply-inbound 时的入库库位")

    args = ap.parse_args()
    db_path = Path(args.db)

    if not db_path.exists():
        raise SystemExit(f"数据库不存在：{db_path}")

    conn = connect(db_path)
    try:
        init_db(conn)  # 幂等补齐结构/触发器/视图
        if args.cmd == "init-locations":
            cabinets = [
                {"code": "G01", "shelves": args.g01_shelves, "note": "三层柜 30cm深x80cm长x35cm高"},
                {"code": "G02", "shelves": args.g02_shelves, "note": "一层柜 40cm深x100cm长x40cm高"},
            ]
            n = init_locations(conn, room=args.room, cabinets=cabinets, positions_per_shelf=args.positions, overwrite_note=args.overwrite_note)
            conn.commit()
            print(f"库位初始化完成：写入/确保存在 {n} 个库位（{args.room}）")
            return
        
        if args.cmd == "lcsc":
            datasheets_dir = Path(args.datasheets_dir) if args.datasheets_dir else (db_path.parent / "datasheets")
            item = lcsc_fetch_and_parse(args.url, datasheets_dir)
            part_id = upsert_part(
                conn,
                mpn=item.mpn,
                name=item.desc,              # 你要求：一句话描述
                category=item.category,
                package=item.package,
                params=item.params_text,      # 参数表进 params
                datasheet=item.datasheet_local or item.page_url,
                note=item.note,
            )
            conn.commit()
            print(f"导入完成：mpn={item.mpn} part_id={part_id}")
            print(f"datasheet={item.datasheet_local or item.page_url}")
            return

        if args.cmd == "stock-in":
            add_stock(conn, args.mpn, args.loc, args.qty, args.condition, args.note)
            conn.commit()
            print(f"入库成功：{args.mpn} @ {args.loc} +{args.qty}")
            return

        if args.cmd == "proj-new":
            create_project(conn, args.code, args.name, args.owner, args.note)
            conn.commit()
            print(f"项目创建成功：{args.code} {args.name}")
            return

        if args.cmd == "bom-set":
            set_bom(conn, args.proj, args.mpn, args.req, args.priority, args.note)
            conn.commit()
            print(f"BOM已更新：{args.proj} {args.mpn} req={args.req}")
            return

        if args.cmd == "reserve":
            alloc_id = reserve_loc(conn, args.proj, args.mpn, args.loc, args.qty, args.note)
            conn.commit()
            print(f"预留成功：alloc_id={alloc_id} {args.proj} {args.mpn} {args.loc} +{args.qty}")
            return

        if args.cmd == "release":
            release_alloc(conn, args.id, args.note)
            conn.commit()
            print(f"释放成功：alloc_id={args.id}")
            return

        if args.cmd == "consume":
            consume_alloc(conn, args.id, args.note)
            conn.commit()
            print(f"消耗成功：alloc_id={args.id}")
            return

        if args.cmd == "proj-status":
            show_project_status(conn, args.proj)
            return

        if args.cmd == "proj-alloc":
            show_alloc_detail(conn, args.proj)
            return

        if args.cmd == "proj-forms":
            export_project_forms(
                conn,
                project_code=args.proj,
                outbound_csv=Path(args.outbound_csv),
                inbound_csv=Path(args.inbound_csv),
                lcsc_file=Path(args.lcsc_file) if args.lcsc_file else None,
                inbound_location=args.inbound_loc,
                apply_inbound=args.apply_inbound,
            )
            if args.apply_inbound:
                conn.commit()
            print(f"出库单已生成：{args.outbound_csv}")
            print(f"入库单已生成：{args.inbound_csv}")
            if args.apply_inbound:
                print(f"已按入库单写库：loc={args.inbound_loc}")
            return

    except sqlite3.IntegrityError as e:
        # 触发器/约束报错通常在这里
        conn.rollback()
        raise SystemExit(f"数据库约束失败：{e}")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
