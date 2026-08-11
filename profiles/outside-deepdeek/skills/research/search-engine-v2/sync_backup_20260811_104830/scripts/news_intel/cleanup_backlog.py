"""cleanup_backlog.py — C 级 (<60分) 老文章清理

背景: news_intelligence 积压 18K+ C 级 (低分) 文章, 拖慢 Step 1 全量统计。
C 级不参与聚合 (仅 A/B 聚合), 不重评, 无 event_id 引用 → 删除安全。

策略 (默认 --days 7):
  删除 scored_at < now-Nd 的 C 级 intel + 其 news_content + 删除后成为孤儿的 rss_raw。
  删除前整库备份到 news_intel.db.backup-cleanup-<ts>。

用法:
  python cleanup_backlog.py --dry-run                # 只统计 (默认)
  python cleanup_backlog.py --commit --days 7        # 实际删除 (先备份)
"""
import argparse
import os
import sqlite3
import shutil
import sys
import datetime


def _db_path(args):
    if args.db:
        return args.db
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "news_intel.db")


def main():
    ap = argparse.ArgumentParser(description="C 级老文章清理")
    ap.add_argument("--db", default=None, help="news_intel.db 路径 (默认本脚本同目录)")
    ap.add_argument("--days", type=int, default=7, help="保留窗口 (天), 默认 7")
    ap.add_argument("--dry-run", action="store_true", default=True, help="只统计 (默认)")
    ap.add_argument("--commit", action="store_true", help="实际删除 (将先备份)")
    args = ap.parse_args()

    db_path = _db_path(args)
    if not os.path.exists(db_path):
        print(f"[ERROR] db 不存在: {db_path}")
        sys.exit(1)

    cutoff = f"datetime('now', '-{args.days} days', 'localtime')"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 目标 C 级 intel (7 天前)
    cur.execute(f"SELECT id, raw_id FROM news_intelligence WHERE tier='C' AND scored_at < {cutoff}")
    rows = cur.fetchall()
    ids = [r[0] for r in rows]
    raw_ids = [r[1] for r in rows if r[1] is not None]

    if not ids:
        print("[ok] 无 C 级老文章可清理")
        conn.close()
        return

    # 关联清理量统计 (删除 intel 后成为孤儿的 rss_raw)
    n_content = cur.execute(
        f"SELECT COUNT(*) FROM news_content WHERE intel_id IN ("
        f"SELECT id FROM news_intelligence WHERE tier='C' AND scored_at < {cutoff})"
    ).fetchone()[0]
    n_raw_orphan = 0
    if raw_ids:
        keep = cur.execute(
            "SELECT DISTINCT raw_id FROM news_intelligence "
            "WHERE raw_id IS NOT NULL AND id NOT IN (%s)"
            % ",".join("?" * len(ids)), ids
        ).fetchall()
        keep_set = {r[0] for r in keep}
        n_raw_orphan = sum(1 for rid in raw_ids if rid not in keep_set)

    print(f"[dry-run] 待清理 C 级(>{args.days}天): intel={len(ids)}, news_content={n_content}, rss_raw孤儿={n_raw_orphan}")
    print(f"[dry-run] 库体积 {os.path.getsize(db_path)//1024//1024} MB")

    if not args.commit:
        print("[dry-run] 未执行删除。确认后加 --commit 实际删除 (将先整库备份)。")
        conn.close()
        return

    # 备份
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{db_path}.backup-cleanup-{ts}"
    shutil.copy2(db_path, backup)
    print(f"[backup] → {backup}")

    # 删除 (顺序: content → intel → 孤儿 raw)
    cur.execute(f"DELETE FROM news_content WHERE intel_id IN ("
                f"SELECT id FROM news_intelligence WHERE tier='C' AND scored_at < {cutoff})")
    cur.execute(f"DELETE FROM news_intelligence WHERE tier='C' AND scored_at < {cutoff}")
    if raw_ids:
        ph = ",".join("?" * len(raw_ids))
        cur.execute(f"DELETE FROM rss_raw WHERE id IN ({ph}) AND id NOT IN "
                    f"(SELECT raw_id FROM news_intelligence WHERE raw_id IS NOT NULL)", raw_ids)
    conn.commit()

    # VACUUM 回收空间
    cur.execute("VACUUM")
    conn.close()
    print(f"[done] 删除 intel={len(ids)}, content={n_content}, raw={n_raw_orphan}; VACUUM 完成")


if __name__ == "__main__":
    main()
