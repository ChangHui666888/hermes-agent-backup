#!/usr/bin/env python3
"""
repair_published_dates.py — 修复 rss-archive.db / news_intel.db 截断的 published_at

背景 (ISS-2026-0901): 2026-07 下旬 scanner 曾把 RSS RFC 日期截断成前 10 字符
('Wed, 29 Ju') 写入 rss_articles.date; 2026-08-15 的 +8h 迁移明确跳过了这类
"损坏/日期-only" 行, 导致这些日期一直不可解析 → 事件聚合时 _parse_date 失败,
last_updated 回退成聚合运行时间 (全事件几乎相同)。

修复规则 (全链路统一 naive 北京时间, 见 beijing-timezone-2026-08-15):
  1. URL 含 /YYYY/M/D/ → 恢复为 YYYY-MM-DDT12:00:00 (北京 naive, 正午避开日界歧义)
  2. 否则 → 用 rss_articles.created_at (扫描时刻, datetime('now','localtime')=北京) 兜底
  3. 同时更新 rss-archive.db (源头, 防未来 sync 再带入) 与 news_intel.db rss_raw

用法:
  python repair_published_dates.py --dry-run   # 只统计, 不改
  python repair_published_dates.py             # 实际修复 (先自动备份 .bak)
"""

import os
import re
import sys
import shutil
import sqlite3
import argparse
from datetime import datetime
from email.utils import parsedate_to_datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "news_intel", "news_intel.db")
ARCHIVE_DB = os.path.expanduser("~/.hermes/rss-archive.db")

URL_DATE_RE = re.compile(r"/(\d{4})/(\d{1,2})/(\d{1,2})/")
TRUNCATED_RE = re.compile(r"^\w{3}, \d{1,2} \w{2,3}$")  # 如 'Wed, 29 Ju'


def is_unparseable(date_str: str) -> bool:
    """无法解析为 ISO 或 RFC 日期 → 视为损坏 (截断/空/乱码)。"""
    if not date_str:
        return True
    try:
        datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return False
    except ValueError:
        pass
    try:
        if parsedate_to_datetime(date_str.strip()):
            return False
    except Exception:
        pass
    return True


def url_recovered(url: str) -> str | None:
    """URL /YYYY/M/D/ → 'YYYY-MM-DDT12:00:00' (北京 naive)。"""
    m = URL_DATE_RE.search(url or "")
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return f"{y:04d}-{mo:02d}-{d:02d}T12:00:00"
    except Exception:
        return None


def created_at_to_iso(created_at: str) -> str | None:
    """'YYYY-MM-DD HH:MM:SS' (北京 localtime) → 'YYYY-MM-DDTHH:MM:SS'。"""
    if not created_at:
        return None
    s = str(created_at).strip().replace(" ", "T")
    try:
        datetime.fromisoformat(s)
        return s
    except ValueError:
        return None


def _backup(path: str):
    bak = path + ".bak-date-repair"
    if os.path.exists(path) and not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"  [backup] {path} -> {bak}")


def repair_archive(dry_run: bool) -> dict:
    """修复 rss-archive.db rss_articles.date。"""
    if not os.path.exists(ARCHIVE_DB):
        print(f"[skip] {ARCHIVE_DB} 不存在")
        return {"total": 0, "url": 0, "created": 0, "empty_skip": 0}
    if not dry_run:
        _backup(ARCHIVE_DB)
    conn = sqlite3.connect(ARCHIVE_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, date, link, created_at FROM rss_articles"
    ).fetchall()
    fix_url = fix_created = empty_skip = 0
    for r in rows:
        if not is_unparseable(r["date"] or ""):
            continue
        if not (r["date"] or ""):
            empty_skip += 1
        from_url = url_recovered(r["link"])
        new_date = from_url or created_at_to_iso(r["created_at"])
        if not new_date:
            continue
        if not dry_run:
            conn.execute("UPDATE rss_articles SET date=? WHERE id=?", (new_date, r["id"]))
        if from_url:
            fix_url += 1
        else:
            fix_created += 1
    conn.commit()
    conn.close()
    return {"total": sum([1 for r in rows if is_unparseable(r["date"] or "")]),
            "url": fix_url, "created": fix_created, "empty_skip": empty_skip}


def repair_news_intel(dry_run: bool) -> dict:
    """修复 news_intel.db rss_raw.published_at (基于 rss-archive 修复后的 date)。"""
    if not os.path.exists(DB_PATH):
        print(f"[skip] {DB_PATH} 不存在")
        return {"total": 0, "url": 0, "created": 0}
    if not dry_run:
        _backup(DB_PATH)
    arch = sqlite3.connect(ARCHIVE_DB)
    # link -> 修复后 date
    arch_map = {r[0]: r[1] for r in arch.execute(
        "SELECT link, date FROM rss_articles WHERE date != ''")}
    arch.close()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, published_at, article_url FROM rss_raw WHERE published_at IS NOT NULL"
    ).fetchall()
    fix_url = fix_created = total = 0
    for r in rows:
        if not is_unparseable(r["published_at"] or ""):
            continue
        total += 1
        new_date = url_recovered(r["article_url"]) or arch_map.get(r["article_url"]) \
            or created_at_to_iso(r["published_at"])
        if not new_date:
            continue
        if not dry_run:
            conn.execute("UPDATE rss_raw SET published_at=? WHERE id=?", (new_date, r["id"]))
        if url_recovered(r["article_url"]):
            fix_url += 1
        else:
            fix_created += 1
    conn.commit()
    conn.close()
    return {"total": total, "url": fix_url, "created": fix_created}


def main():
    p = argparse.ArgumentParser(description="修复截断的 published_at 日期 (北京时间 naive)")
    p.add_argument("--dry-run", action="store_true", help="只统计不改")
    args = p.parse_args()
    mode = "DRY-RUN(只统计)" if args.dry_run else "修复"
    print(f"===== 修复截断 published_at [{mode}] =====")
    a = repair_archive(args.dry_run)
    n = repair_news_intel(args.dry_run)
    print(f"[rss-archive] 损坏日期 {a['total']} | URL恢复 {a['url']} | created_at兜底 {a['created']} | 空值跳过 {a['empty_skip']}")
    print(f"[news_intel]  损坏日期 {n['total']} | URL恢复 {n['url']} | created_at兜底 {n['created']}")
    if args.dry_run:
        print("\n确认无误后运行: python repair_published_dates.py")


if __name__ == "__main__":
    main()
