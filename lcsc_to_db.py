import argparse
import re
import sqlite3
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


def clean_text(s: str) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def normalize_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


def safe_filename(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", "_", name)
    return name[:180] if len(name) > 180 else name


def fetch_html(session: requests.Session, url: str) -> str:
    r = session.get(url, timeout=20)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


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
        if lines[i].startswith("属性") and "参数值" in lines[i]:
            start_idx = i + 1
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
        if key and val and key not in {"属性", "参数值"}:
            if key not in pairs:
                pairs[key] = val
        i += 2
    return pairs


def find_datasheet_url(soup: BeautifulSoup, base_url: str) -> str:
    candidates = []

    # 1) 链接文本包含“数据手册/Datasheet”
    for a in soup.find_all("a", href=True):
        txt = clean_text(a.get_text(" ", strip=True))
        href = a["href"]
        full = urljoin(base_url, href)
        if re.search(r"(数据手册|Datasheet)", txt, re.I):
            candidates.append(full)

    # 2) href 里包含 pdf
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base_url, href)
        if ".pdf" in full.lower():
            if re.search(r"(datasheet|data\s*sheet|规格书|说明书|手册)", full, re.I):
                candidates.append(full)
            else:
                candidates.append(full)

    # 3) 兜底：从页面源码里抓 pdf
    raw = str(soup)
    for m in re.finditer(r"https?://[^\s\"']+\.pdf", raw, flags=re.I):
        candidates.append(m.group(0))

    # 去重
    uniq, seen = [], set()
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

        # 如果 content-type 不像 pdf，就检查开头是不是 %PDF-
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


def upsert_part(
    conn: sqlite3.Connection,
    mpn: str,
    name: str,
    category: str,
    package: str,
    params_text: str,
    datasheet: str,
    note: str,
) -> int:
    cur = conn.cursor()
    cur.execute("SELECT id FROM parts WHERE mpn = ?", (mpn,))
    row = cur.fetchone()
    if row:
        part_id = row[0]
        cur.execute(
            """
            UPDATE parts
            SET name = COALESCE(NULLIF(?, ''), name),
                category = COALESCE(NULLIF(?, ''), category),
                package = COALESCE(NULLIF(?, ''), package),
                params = COALESCE(NULLIF(?, ''), params),
                datasheet = COALESCE(NULLIF(?, ''), datasheet),
                note = COALESCE(NULLIF(?, ''), note)
            WHERE id = ?
            """,
            (name, category, package, params_text, datasheet, note, part_id),
        )
    else:
        cur.execute(
            """
            INSERT INTO parts (mpn, name, category, package, params, datasheet, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (mpn, name, category, package, params_text, datasheet, note),
        )
        part_id = cur.lastrowid
    return part_id


def upsert_stock(conn: sqlite3.Connection, part_id: int, location: str, qty: int):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, qty FROM stock WHERE part_id = ? AND location = ?",
        (part_id, location),
    )
    row = cur.fetchone()
    if row:
        stock_id, old_qty = row
        cur.execute(
            """
            UPDATE stock
            SET qty = ?, updated_at = datetime('now','localtime')
            WHERE id = ?
            """,
            (int(old_qty) + qty, stock_id),
        )
    else:
        cur.execute(
            """
            INSERT INTO stock (part_id, location, qty)
            VALUES (?, ?, ?)
            """,
            (part_id, location, qty),
        )


def main():
    ap = argparse.ArgumentParser(description="从立创商品页抓取信息并写入本地SQLite库存数据库（含自动下载数据手册）")
    ap.add_argument("--db", required=True, help=r"数据库路径，例如 G:\LabInventory\lab_inventory.db")
    ap.add_argument("--url", required=True, help="立创商品链接，例如 https://item.szlcsc.com/8143.html")
    ap.add_argument("--location", default="", help="库位，例如 C409-G01-S01-P01；不填则不写入 stock")
    ap.add_argument("--qty", type=int, default=0, help="数量；配合 --location 使用")
    ap.add_argument("--datasheets_dir", default="", help=r"数据手册保存目录，例如 G:\LabInventory\datasheets")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"数据库不存在：{db_path}")

    datasheets_dir = Path(args.datasheets_dir) if args.datasheets_dir else (db_path.parent / "datasheets")

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9",
    })

    url = normalize_url(args.url)
    html = fetch_html(session, url)
    soup = BeautifulSoup(html, "lxml")

    mpn = find_value_by_label(soup, "商品型号")
    if not mpn:
        t = soup.get_text("\n", strip=True)
        m = re.search(r"商品型号\s*[:：]?\s*([A-Za-z0-9\-_.]+)", t)
        mpn = m.group(1) if m else ""
    if not mpn:
        raise SystemExit("解析失败：没找到 商品型号（mpn）。")

    # name：一句话描述
    desc = find_value_by_label(soup, "描述")
    name = desc or mpn

    brand = find_value_by_label(soup, "品牌名称")
    lcsc_code = find_value_by_label(soup, "商品编号")
    package = find_value_by_label(soup, "商品封装")
    category = find_value_by_label(soup, "商品目录") or "未分类"

    # 商品参数表 → params
    params = parse_params_table(soup)
    params_text = "; ".join([f"{k}={v}" for k, v in params.items()]) if params else ""

    # note：只放追溯信息（不放参数表）
    note_parts = []
    if brand:
        note_parts.append(f"品牌={brand}")
    if lcsc_code:
        note_parts.append(f"LCSC={lcsc_code}")
    note_parts.append(f"URL={url}")

    # datasheet：默认写商品页 URL，若下载成功则写本地路径
    datasheet_value = url

    pdf_url = find_datasheet_url(soup, url)
    if pdf_url:
        base_name = safe_filename(mpn)
        if lcsc_code:
            base_name += f"__{safe_filename(lcsc_code)}"
        out_pdf = datasheets_dir / f"{base_name}.pdf"
        try:
            ok = download_pdf(session, pdf_url, out_pdf)
            if ok:
                datasheet_value = str(out_pdf)
                note_parts.append(f"DatasheetPDF={pdf_url}")
            else:
                note_parts.append(f"DatasheetPDF下载失败={pdf_url}")
        except Exception as e:
            note_parts.append(f"DatasheetPDF异常={pdf_url} ({type(e).__name__})")
    else:
        note_parts.append("DatasheetPDF未找到")

    note = " | ".join(note_parts)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        part_id = upsert_part(conn, mpn, name, category, package, params_text, datasheet_value, note)
        if args.location and args.qty:
            upsert_stock(conn, part_id, args.location, int(args.qty))
        conn.commit()
    finally:
        conn.close()

    print("写入完成：")
    print(f"  mpn={mpn}")
    print(f"  name={name}")
    print(f"  category={category}")
    print(f"  package={package}")
    print(f"  params={params_text[:120]}{'...' if len(params_text) > 120 else ''}")
    print(f"  part_id={part_id}")
    print(f"  datasheet={datasheet_value}")
    if args.location and args.qty:
        print(f"  入库：{args.location} +{args.qty}")


if __name__ == "__main__":
    main()
