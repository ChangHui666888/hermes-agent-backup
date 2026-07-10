#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# News Pipeline — triggered by Hermes cron
# Lives alongside news_intel/ for clean imports

import argparse
import logging
import os
import sys

os.environ["PYTHONUNBUFFERED"] = "1"
os.environ.setdefault("NEWS_API_BASE", "http://100.107.117.23:8001")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("pipeline")

# 退出状态码
EXIT_OK = 0
EXIT_PIPELINE = 1
EXIT_IMPORT = 2
EXIT_CONFIG = 3


def print_summary(report: dict):
    """动态输出摘要 — 不硬编码 Tier 名称"""
    report = report or {}
    tiers = {
        "tier_a": "DeepSeek V4 Flash",
        "tier_b": "Qwen3-1.7B",
        "tier_c": "Python 规则",
    }

    print()
    print("📊 News Pipeline Summary")
    print(f"  Processed  : {report.get('processed', 0)}")
    for key, label in tiers.items():
        cnt = report.get(key, 0)
        if cnt:
            print(f"  {label:>16s}: {cnt}")
    print(f"  Duplicate  : {report.get('duplicate', 0)}")
    print(f"  Enhanced   : {report.get('enhanced', 0)}")
    print(f"  Saved      : {report.get('saved', 0)}")
    print(f"  Failed     : {report.get('failed', 0)}")
    print(f"  Duration   : {report.get('duration_sec', 0)}s")
    print()


def main():
    parser = argparse.ArgumentParser(description="News Intelligence Pipeline")
    parser.add_argument("--hours", type=int, default=1)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    logger.info("Starting News Pipeline")

    try:
        from news_intel.pipeline import run_pipeline
    except ImportError:
        logger.exception("Import failed — check PYTHONPATH")
        return EXIT_IMPORT

    try:
        report = run_pipeline(hours=args.hours, limit=args.limit) or {}
        logger.info("Pipeline finished")
        print_summary(report)
        return EXIT_OK
    except Exception:
        logger.exception("Pipeline failed")
        return EXIT_PIPELINE


if __name__ == "__main__":
    sys.exit(main())
