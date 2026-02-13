#!/usr/bin/env python3
"""将 BoM Excel 清洗后导入 SQLite parts 表（支持 upsert 与 dry-run）。"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup


EXPECTED_COLUMN_ALIASES = {
    "ID": ["ID"],
    "Name Manufacturer Part": ["Name Manufacturer Part", "Name"],
    "Designator": ["Designator"],
    "Footprint 封装 Footprint": ["Footprint 封装 Footprint"],
    "Quantity": ["Quantity"],
    "Manufacturer Part": ["Manufacturer Part", "型号 Manufacturer Part", "型号"],
    "Manufacturer": ["Manufacturer", "品牌 Manufacturer", "品牌"],
    "Supplier": ["Supplier"],
    "Supplier Part": ["Supplier Part"],
    "商品名称": ["商品名称", "商品名称.1", "商品名称.2"],
    "参数": ["参数", "参数.1"],
    "目录": ["目录", "目录.1"],
    "商品链接": ["商品链接", "商品链接.1"],
    "封装": ["封装", "封装 Footprint", "Footprint 封装 Footprint"],
}

REQUIRED_IMPORT_COLUMNS = ["Manufacturer Part", "商品名称", "商品链接", "目录", "封装", "参数", "Manufacturer", "Quantity"]


@dataclass
class Stats:
    total_rows: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0


class ImportErrorFatal(Exception):
    pass


def resolve_input_path(raw_path: str, cwd: Path) -> Path:
    """兼容 Windows 路径输入（如 G:/LabInventory/xxx）并映射到当前仓库。"""
    candidate = Path(raw_path)
    if candidate.exists():
        return candidate

    normalized = raw_path.replace('\\', '/')
    mapped = Path(normalized)
    if mapped.exists():
        return mapped

    m = re.match(r'^[A-Za-z]:/LabInventory/(.+)$', normalized)
    if m:
        local = cwd / m.group(1)
        if local.exists():
            return local

    local_by_name = cwd / Path(normalized).name
    if local_by_name.exists():
        return local_by_name

    return candidate


def resolve_output_dir(raw_path: str, cwd: Path) -> Path:
    candidate = Path(raw_path)
    if os.name == 'nt':
        return candidate

    normalized = raw_path.replace('\\', '/')
    m = re.match(r'^[A-Za-z]:/LabInventory/(.+)$', normalized)
    if m:
        return cwd / m.group(1)
    return Path(normalized)


def parse_sheet_arg(sheet_arg: str):
    sheet_text = str(sheet_arg).strip()
    return int(sheet_text) if sheet_text.isdigit() else sheet_text

def clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    s = re.sub(r"\s+", " ", str(value)).strip()
    return s or None


def normalize_url(url: str | None) -> str | None:
    url = clean_text(url)
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme:
        return f"https://{url}"
    return url


def parse_qty(value: Any) -> float | None:
    value = clean_text(value)
    if value is None:
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError as exc:
        raise ValueError(f"Quantity 不是有效数字: {value}") from exc


def choose_column(row: pd.Series, candidates: list[str]) -> Any:
    candidate_set = set(candidates)
    for col in candidates:
        if col in row.index:
            val = row[col]
            if not pd.isna(val):
                t = clean_text(val)
                if t:
                    return t

    # 兼容重复列名被 pandas 自动改写成 `.1`、`.2` 的情况
    for col in row.index:
        if base_col_name(str(col)) not in candidate_set:
            continue
        val = row[col]
        if not pd.isna(val):
            t = clean_text(val)
            if t:
                return t
    return None


def base_col_name(col: str) -> str:
    return re.sub(r"\.\d+$", "", col)


def validate_headers(columns: list[str]) -> None:
    base_counts = Counter(base_col_name(c) for c in columns)
    missing = []
    for logical_name, aliases in EXPECTED_COLUMN_ALIASES.items():
        if not any(alias in base_counts for alias in aliases):
            missing.append(f"{logical_name} (可接受列名: {', '.join(aliases)})")

    if missing:
        raise ImportErrorFatal("Excel 列校验失败，存在缺失列：\n- " + "\n- ".join(missing))

    missing_required = [x for x in REQUIRED_IMPORT_COLUMNS if x not in base_counts]
    if missing_required:
        raise ImportErrorFatal("导入关键列缺失：" + ", ".join(missing_required))


def get_parts_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    if not rows:
        raise ImportErrorFatal(f"数据库中不存在表 `{table_name}`。")
    return {r[1] for r in rows}


def detect_unique_key(conn: sqlite3.Connection, table_name: str, cols: set[str]) -> str:
    if "part_number" in cols:
        return "part_number"
    if "mpn" in cols:
        return "mpn"

    # 兜底：从唯一索引中找单列索引
    idx_list = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
    for idx in idx_list:
        idx_name = idx[1]
        is_unique = idx[2]
        if not is_unique:
            continue
        idx_cols = conn.execute(f"PRAGMA index_info({idx_name})").fetchall()
        if len(idx_cols) == 1:
            return idx_cols[0][2]

    raise ImportErrorFatal(
        f"无法识别 `{table_name}` 的唯一键（期望包含 part_number 或 mpn）。"
    )


def find_datasheet_pdf_url(session: requests.Session, page_url: str) -> str | None:
    try:
        resp = session.get(page_url, timeout=20)
        resp.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    candidates: list[tuple[int, str]] = []
    blocklist = ("iso_iec_doc", "isoiec", "certificate", "认证", "rohs", "reach")

    def score_and_add(url: str, text: str = "") -> None:
        if not url:
            return
        lower_full = url.lower()
        if ".pdf" not in lower_full:
            return
        if any(x in lower_full for x in blocklist):
            return

        lower_text = (text or "").lower()
        score = 0
        if re.search(r"datasheet|data\s*sheet|数据手册|规格书|说明书|手册", lower_text, re.I):
            score += 5
        if re.search(r"datasheet|data\s*sheet|规格书|manual", lower_full, re.I):
            score += 3
        if lower_full.endswith('.pdf'):
            score += 2
        candidates.append((score, url))

    for a in soup.find_all("a", href=True):
        href = clean_text(a.get("href"))
        if not href:
            continue
        full = urljoin(page_url, href)
        txt = clean_text(a.get_text(" ", strip=True)) or ""
        score_and_add(full, txt)

    # 页面脚本中有时直接包含 pdf 链接
    raw = resp.text
    for m in re.finditer(r'https?://[^\s"\']+\.pdf(?:\?[^\s"\']*)?', raw, flags=re.I):
        score_and_add(m.group(0), "")

    if not candidates:
        return None

    # 去重并按得分排序
    dedup: dict[str, int] = {}
    for score, url in candidates:
        dedup[url] = max(score, dedup.get(url, -1))

    best_url, best_score = max(dedup.items(), key=lambda item: item[1])
    return best_url if best_score > 0 else None


def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")


def download_pdf(session: requests.Session, pdf_url: str, target: Path, referer: str | None = None) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    headers = {"Referer": referer} if referer else {}
    try:
        with session.get(pdf_url, timeout=30, stream=True, headers=headers) as resp:
            resp.raise_for_status()
            content_type = (resp.headers.get("Content-Type") or "").lower()
            first_chunk = b""
            with target.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 128):
                    if not chunk:
                        continue
                    if not first_chunk:
                        first_chunk = chunk[:8]
                    f.write(chunk)
            is_pdf = ("pdf" in content_type) or first_chunk.startswith(b"%PDF-")
        return is_pdf and target.exists() and target.stat().st_size > 1024
    except Exception:
        return False


def log_line(log_fp, msg: str) -> None:
    log_fp.write(msg + "\n")
    log_fp.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="导入 BoM 到 lab_inventory.db")
    parser.add_argument("--db", required=True, help="SQLite 数据库路径")
    parser.add_argument("--xlsx", required=True, help="BoM xlsx 路径")
    parser.add_argument("--sheet", default=0, help="sheet 名称或索引（默认第一个）")
    parser.add_argument("--dry-run", action="store_true", help="仅校验与预演，不提交")
    parser.add_argument("--log", default="./import_log.txt", help="日志输出文件路径")
    parser.add_argument(
        "--datasheets-dir",
        default="G:/LabInventory/datasheets",
        help="datasheet PDF 保存目录",
    )
    args = parser.parse_args()

    cwd = Path.cwd()
    db_path = resolve_input_path(args.db, cwd)
    xlsx_path = resolve_input_path(args.xlsx, cwd)
    log_path = Path(args.log)
    datasheets_dir = resolve_output_dir(args.datasheets_dir, cwd)

    stats = Stats()

    with log_path.open("w", encoding="utf-8") as log_fp:
        log_line(log_fp, "=== BoM 导入日志 ===")
        log_line(log_fp, f"DB: {db_path}")
        log_line(log_fp, f"XLSX: {xlsx_path}")
        if args.db != str(db_path) or args.xlsx != str(xlsx_path):
            log_line(log_fp, f"路径映射: db={args.db} -> {db_path}; xlsx={args.xlsx} -> {xlsx_path}")
        log_line(log_fp, f"Sheet: {args.sheet}")
        log_line(log_fp, f"Dry-run: {args.dry_run}")

        if not db_path.exists():
            raise ImportErrorFatal(f"数据库文件不存在: {db_path}")
        if not xlsx_path.exists():
            raise ImportErrorFatal(f"Excel 文件不存在: {xlsx_path}")

        sheet_name = parse_sheet_arg(args.sheet)
        df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=5, dtype=object)
        validate_headers(df.columns.tolist())

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        try:
            table_name = "parts"
            part_cols = get_parts_table_columns(conn, table_name)
            unique_key = detect_unique_key(conn, table_name, part_cols)
            log_line(log_fp, f"目标表: {table_name}; 唯一键: {unique_key}")

            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9",
            })
            conn.execute("BEGIN")

            for idx, row in df.iterrows():
                stats.total_rows += 1
                excel_line = idx + 7  # excel 可见行号（header=6）
                try:
                    mpn = choose_column(row, ["Manufacturer Part", "型号 Manufacturer Part", "型号"])
                    name = choose_column(row, ["商品名称", "Name"])
                    url = normalize_url(choose_column(row, ["商品链接"]))
                    category = choose_column(row, ["目录"])
                    package = choose_column(row, ["封装", "封装 Footprint", "Footprint 封装 Footprint"])
                    params = choose_column(row, ["参数", "参数.1"])
                    note = choose_column(row, ["Manufacturer"])
                    supplier_part = choose_column(row, ["Supplier Part"])
                    qty = parse_qty(choose_column(row, ["Quantity"]))

                    if qty is None:
                        stats.skipped += 1
                        log_line(log_fp, f"[SKIP] 行 {excel_line}: Quantity 为空或无效")
                        continue

                    if not mpn:
                        stats.skipped += 1
                        log_line(log_fp, f"[SKIP] 行 {excel_line}: Manufacturer Part 为空")
                        continue
                    if not name or not category:
                        stats.skipped += 1
                        log_line(log_fp, f"[SKIP] 行 {excel_line}: 商品名称或目录为空, mpn={mpn}")
                        continue

                    datasheet_local = None
                    if url:
                        pdf_url = find_datasheet_pdf_url(session, url)
                        if pdf_url:
                            if supplier_part:
                                filename = safe_filename(f"{mpn}__{supplier_part}.pdf")
                            else:
                                filename = safe_filename(f"{mpn}.pdf")
                            pdf_path = datasheets_dir / filename
                            if download_pdf(session, pdf_url, pdf_path, referer=url):
                                datasheet_local = str(pdf_path)
                            else:
                                log_line(log_fp, f"[WARN] 行 {excel_line}: datasheet 下载失败 {pdf_url}")
                        else:
                            log_line(log_fp, f"[WARN] 行 {excel_line}: 未找到 datasheet 链接")

                    existed = conn.execute(
                        f"SELECT id, created_at FROM {table_name} WHERE {unique_key}=?",
                        (mpn,),
                    ).fetchone()

                    if existed:
                        update_fields = ["name=?", "url=?", "category=?", "package=?", "params=?", "note=?"]
                        update_values = [name, url, category, package, params, note]
                        if datasheet_local:
                            update_fields.append("datasheet=?")
                            update_values.append(datasheet_local)
                        if "updated_at" in part_cols:
                            update_fields.append("updated_at=datetime('now','localtime')")
                        update_values.append(mpn)
                        conn.execute(
                            f"UPDATE {table_name} SET {', '.join(update_fields)} WHERE {unique_key}=?",
                            update_values,
                        )
                        stats.updated += 1
                    else:
                        insert_cols = [unique_key, "name", "url", "category", "package", "params", "note", "datasheet"]
                        insert_values = [mpn, name, url, category, package, params, note, datasheet_local]
                        ph = ",".join(["?"] * len(insert_cols))
                        conn.execute(
                            f"INSERT INTO {table_name} ({','.join(insert_cols)}) VALUES ({ph})",
                            insert_values,
                        )
                        stats.inserted += 1

                except Exception as row_exc:
                    stats.failed += 1
                    log_line(log_fp, f"[ERROR] 行 {excel_line}: {row_exc}")

            if args.dry_run:
                conn.rollback()
                log_line(log_fp, "[INFO] dry-run 已回滚，未写入数据库。")
            else:
                conn.commit()
                log_line(log_fp, "[INFO] 已提交事务。")

        except Exception as fatal:
            conn.rollback()
            log_line(log_fp, f"[FATAL] {fatal}")
            raise
        finally:
            conn.close()

        summary = (
            f"总行数={stats.total_rows}, 插入={stats.inserted}, 更新={stats.updated}, "
            f"跳过={stats.skipped}, 失败={stats.failed}"
        )
        log_line(log_fp, "=== 统计 ===")
        log_line(log_fp, summary)

    print("导入完成：" + summary)
    print("SQL 检查语句：")
    print("1) SELECT COUNT(*) AS parts_count FROM parts;")
    print("2) SELECT mpn, name, url FROM parts WHERE mpn = 'SN74LVC1G08DBVR';")
    print(f"日志文件：{log_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImportErrorFatal as exc:
        print(f"导入失败：{exc}", file=sys.stderr)
        raise SystemExit(2)
