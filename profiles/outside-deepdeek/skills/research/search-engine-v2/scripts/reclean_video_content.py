#!/usr/bin/env python3
"""
reclean_video_content.py — 一次性脚本: 批量重清洗 news_content 中已有的视频内容

背景: 视频内容清洗器 (fetch_browser/extract_single 的 _clean_video_content) 于
2026-07-31 部署。在此之前抓取的视频行 (尤其 jina 整页 20 万字噪音) 未清洗入库。
本脚本对历史视频行套用清洗器, 更新 content_md + content_len。

特性:
- 幂等: 对已清洗内容重跑是无操作, 可安全重复执行
- 备份: 改写前把原始 content_md 导出到 JSONL 备份文件
- --dry-run: 只统计不改写

用法:
  python reclean_video_content.py               # 默认生产库 (脚本目录 news_intel/news_intel.db)
  python reclean_video_content.py --db <path>   # 指定库
  python reclean_video_content.py --dry-run     # 预览不落库
"""

import sys, os, json, sqlite3, argparse
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, "core"))

from core.fetchers import _clean_video_content, _get_crawl_config

DEFAULT_DB = os.path.join(SCRIPT_DIR, "news_intel", "news_intel.db")


def main():
    parser = argparse.ArgumentParser(description="批量重清洗视频内容")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 库路径 (默认: 脚本目录 news_intel/news_intel.db)")
    parser.add_argument("--dry-run", action="store_true", help="只统计不改写")
    parser.add_argument("--backup", default=None, help="备份 JSONL 路径 (默认: 库目录 reclean_backup_{ts}.jsonl)")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"❌ 库不存在: {args.db}")
        sys.exit(1)

    cfg = _get_crawl_config()
    max_len = int(cfg.get("crawl.video_max_content", 20000))
    patterns = cfg.get("crawl.video_patterns", ["/video/", "/videos/"])

    like_conds = " OR ".join("rr.article_url LIKE ?" for _ in patterns)
    like_params = [f"%{p}%" for p in patterns]

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"""
        SELECT nc.id, rr.article_url, nc.content_md, nc.content_len
        FROM news_content nc
        JOIN news_intelligence ni ON nc.intel_id = ni.id
        JOIN rss_raw rr ON ni.raw_id = rr.id
        WHERE ({like_conds})
          AND nc.content_md IS NOT NULL AND nc.content_md != ''
    """, like_params).fetchall()
    total = len(rows)
    print(f"待清洗视频行: {total} | 库: {args.db} | max_len={max_len}")

    changed, skipped, before_chars, after_chars = 0, 0, 0, 0
    backup = []
    for r in rows:
        raw = r["content_md"] or ""
        before_chars += len(raw)
        clean = _clean_video_content(raw, max_len=max_len)
        if clean == raw:
            skipped += 1
            continue
        changed += 1
        after_chars += len(clean)
        backup.append({"id": r["id"], "url": r["article_url"], "content_md": raw})
        if not args.dry_run:
            conn.execute("UPDATE news_content SET content_md=?, content_len=? WHERE id=?",
                         (clean, len(clean), r["id"]))

    if not args.dry_run:
        conn.commit()
        # 备份原始内容
        ts = os.path.basename(args.db).replace(".db", "") or "video"
        backup_path = args.backup or os.path.join(
            os.path.dirname(args.db), f"reclean_backup_{ts}.jsonl")
        with open(backup_path, "w", encoding="utf-8") as f:
            for b in backup:
                f.write(json.dumps(b, ensure_ascii=False) + "\n")
        print(f"✅ 已改写 {changed} 行 (跳过 {skipped}), 备份: {backup_path}")
    else:
        print(f"🔍 dry-run: 将改写 {changed} 行 (跳过 {skipped})")

    print(f"  总字符: {before_chars:,} → {after_chars:,}  (缩减 {100*(before_chars-after_chars)//max(before_chars,1)}%)")
    conn.close()


if __name__ == "__main__":
    main()
