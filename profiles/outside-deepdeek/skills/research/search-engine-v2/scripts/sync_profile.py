#!/usr/bin/env python3
"""sync_profile.py — 开发环境 → 本地生产 profile 同步工具 (2026-08-08)

解决"手动 cp 易漏"痛点：dev→prod 增量同步 + 差异检查 + 备份。

用法:
  python scripts/sync_profile.py --check     # 只查差异 (不写)
  python scripts/sync_profile.py --apply     # 备份差异文件后同步
  python scripts/sync_profile.py --apply --force   # 全量覆盖(不按差异)

环境路径 (env-topology):
  DEV  = workspace/search-engine-v2                  (开发, git 仓库)
  PROD = ~/AppData/Local/hermes/profiles/outside-deepdeek/.../search-engine-v2 (本地生产)
"""
import argparse
import os
import shutil
import sys
from datetime import datetime

DEV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # search-engine-v2
PROD = os.path.expanduser(
    "~/AppData/Local/hermes/profiles/outside-deepdeek/skills/research/search-engine-v2")

# 同步清单: 相对 repo 根的 文件/目录 (目录递归, 含排除规则)
SYNC_LIST = [
    "scripts/news_intel/",          # 流水线核心 (排除运行时产物)
    "scripts/config/",              # 配置包 (loader/env/settings/domain_profiles)
    "scripts/core/",                # 抓取引擎
    "knowledge_base/",              # KB YAML + loader
    "scripts/auto-pipeline.py",
    "scripts/batch.py",
    "scripts/news-pipeline.py",
    "scripts/demo.py",
    "scripts/hermes-cron/config-agent.py",
    "scripts/hermes-cron/rss-scanner.py",
]

# 目录内排除 (文件名/后缀)
EXCLUDE = {
    "__pycache__", ".pyc", ".db", ".db-shm", ".db-wal", ".jsonl",
    ".log", ".csv", ".zip", ".bak", ".tmp", "fact_pipeline_payload.json",
    "ner_by_article.json", "event_registry_bak",
}
# 备份/实验目录段 (不同步到生产)
EXCLUDE_DIR = {"__pycache__", "bk", "data", "experiments"}
# 实验/一次性脚本 (不生产)
EXCLUDE_FILE = {
    "fact_ab_experiment.py", "fact_c_experiment.py", "fact_composite_experiment.py",
    "fact_experiment.py", "fact_extractor_gliner_rebel.py", "fact_hybrid_strategy.py",
    "fact_hybrid_tune.py", "fact_router_eval.py", "apply_review_scores.py",
    "score_review.py", "_selftest.py",
}


def _excluded(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    for p in parts:
        if p in EXCLUDE_DIR:
            return True
    for e in EXCLUDE:
        if rel.endswith(e):
            return True
    if rel.endswith(".json"):
        # v2.3 (2026-08-08): 评分配置 (config/ 下) 允许同步; 其余 .json (运行时/实验产物) 排除
        if rel.startswith("config/") or "/config/" in rel:
            return False
        return True
    if parts and parts[-1] in EXCLUDE_FILE:
        return True
    return False


def _walk(root: str) -> dict:
    """返回 {相对路径: mtime} (递归目录, 排除规则)。"""
    out = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            rel = os.path.relpath(os.path.join(base, f), root).replace("\\", "/")
            if _excluded(rel):
                continue
            out[rel] = os.path.getmtime(os.path.join(base, f))
    return out


def _collect() -> list:
    """收集同步项: [(dev_path, prod_path, rel)]"""
    items = []
    for entry in SYNC_LIST:
        d = os.path.join(DEV, entry)
        p = os.path.join(PROD, entry)
        if not os.path.exists(d):
            print(f"  ⚠️ dev 缺失: {entry}")
            continue
        items.append((d, p, entry))
    return items


def check():
    print(f"DEV : {DEV}")
    print(f"PROD: {PROD}")
    print("=" * 60)
    changed, only_dev, only_prod = [], [], []
    for d, p, rel in _collect():
        if os.path.isfile(d):
            # 单文件: 直接比 mtime (不遍历父目录, 避免 node_modules 等)
            if os.path.exists(p):
                if os.path.getmtime(d) != os.path.getmtime(p):
                    changed.append(rel)
            else:
                only_dev.append(rel)
        else:
            # 目录
            dw = _walk(d)
            if not os.path.isdir(p):
                only_dev.append(rel + "/")
                continue
            pw = _walk(p)
            for k in dw:
                if k not in pw:
                    only_dev.append(rel + "/" + k)
                elif dw[k] != pw[k]:
                    changed.append(rel + "/" + k)
            for k in pw:
                if k not in dw:
                    only_prod.append(rel + "/" + k)
    print(f"差异 {len(changed)} · 仅dev {len(only_dev)} · 仅prod {len(only_prod)}")
    for c in sorted(changed):
        print(f"  🔄 {c}")
    for c in sorted(only_dev):
        print(f"  🆕 {c}")
    for c in sorted(only_prod):
        print(f"  🗑 (prod多余) {c}")
    return changed, only_dev


def apply(force=False):
    bk_root = os.path.join(PROD, f"sync_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    changed, only_dev = check()
    targets = changed if not force else []
    if not force:
        targets = changed
    # 备份 + 同步
    n = 0
    for d, p, rel in _collect():
        if os.path.isfile(d):
            if not force and rel not in targets:
                continue
            _backup_file(p, bk_root)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            shutil.copy2(d, p)
            print(f"  ✅ {rel}")
            n += 1
        else:
            dw = _walk(d)
            pw = _walk(p) if os.path.isdir(p) else {}
            todo = set(dw) | (set(only_dev) if force else set())
            for k in dw:
                if force or k not in pw or dw[k] != pw[k]:
                    sp, tp = os.path.join(d, k), os.path.join(p, k)
                    _backup_file(tp, bk_root)
                    os.makedirs(os.path.dirname(tp), exist_ok=True)
                    shutil.copy2(sp, tp)
                    print(f"  ✅ {rel}{k}")
                    n += 1
    print(f"\n✅ 同步 {n} 项完成 · 备份: {bk_root}")


def _backup_file(fp: str, bk_root: str):
    if os.path.exists(fp):
        bf = os.path.join(bk_root, os.path.relpath(fp, PROD).replace("\\", "/"))
        os.makedirs(os.path.dirname(bf), exist_ok=True)
        shutil.copy2(fp, bf)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="dev→prod profile 同步")
    ap.add_argument("--check", action="store_true", help="只查差异")
    ap.add_argument("--apply", action="store_true", help="备份差异后同步")
    ap.add_argument("--force", action="store_true", help="全量覆盖")
    args = ap.parse_args()
    if args.apply:
        apply(force=args.force)
    else:
        check()
