#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# News Pipeline — triggered by Hermes cron
# Lives alongside news_intel/ for clean imports

import argparse
import logging
import os
import sys

os.environ["PYTHONUNBUFFERED"] = "1"
os.environ.setdefault("NEWS_API_BASE", "http://100.107.117.23")

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
    """动态输出摘要 — 不硬编码 Tier 名称

    注意：这里的 key 必须与 news_intel/pipeline.py::run_pipeline() 里
    实际构造的 report dict 字段名一致（batch_tier_a / batch_tier_b / ...），
    此前这里用的是 processed/tier_a/duplicate/enhanced/saved/failed，
    跟 run_pipeline() 返回的字段完全对不上，导致摘要一直打印 0，
    掩盖了 fetch 阶段从未真正执行的问题。
    """
    report = report or {}
    tiers = {
        "batch_tier_a": "DeepSeek V4 Flash",
        "batch_tier_b": "Qwen3-1.7B",
        "batch_tier_c": "Python 规则",
    }

    print()
    print("📊 News Pipeline Summary")
    print(f"  Batch Input   : {report.get('batch_input', 0)}")
    print(f"  New           : {report.get('batch_new', 0)}")
    print(f"  Duplicate     : {report.get('batch_duplicate', 0)}")
    for key, label in tiers.items():
        cnt = report.get(key, 0)
        if cnt:
            print(f"  {label:>16s}: {cnt}")
    print(f"  Enhanced      : {report.get('batch_enhanced', 0)}")
    print(f"  Pushed        : {report.get('batch_pushed', 0)}")
    print(f"  Push Failed   : {report.get('batch_push_failed', 0)}")
    print(f"  Total Articles: {report.get('total_articles', 0)}")
    print(f"  Duration      : {report.get('duration_sec', 0)}s "
          f"(push: {report.get('duration_push_sec', 0)}s)")
    print()


def main():
    parser = argparse.ArgumentParser(description="News Intelligence Pipeline")
    parser.add_argument("--hours", type=int, default=1)
    parser.add_argument("--limit", type=int, default=100)
    # 根因A修复：之前这里没有 --fetch 开关，run_pipeline() 的 do_fetch
    # 永远走默认值 False，导致 cron 定时任务从未真正调用 batch.py 抓正文。
    # 默认设为 True，这样即使 Windows 计划任务里没有额外加参数，抓取也会生效；
    # 如果想临时跳过抓取（比如只想快速看评分结果），显式传 --no-fetch 即可。
    parser.add_argument(
        "--fetch", dest="fetch", action="store_true", default=True,
        help="抓取正文（默认开启）"
    )
    parser.add_argument(
        "--no-fetch", dest="fetch", action="store_false",
        help="跳过正文抓取，仅评分"
    )
    args = parser.parse_args()

    logger.info(f"Starting News Pipeline (fetch={args.fetch})")

    try:
        from news_intel.pipeline import run_pipeline
    except ImportError:
        logger.exception("Import failed — check PYTHONPATH")
        return EXIT_IMPORT

    try:
        report = run_pipeline(
            hours=args.hours, limit=args.limit, do_fetch=args.fetch
        ) or {}
        logger.info("Pipeline finished")
        print_summary(report)
        return EXIT_OK
    except Exception:
        logger.exception("Pipeline failed")
        return EXIT_PIPELINE


if __name__ == "__main__":
    sys.exit(main())
