#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
News Pipeline — Hermes cron wrapper

Responsibilities:
- bootstrap environment
- configure logging
- execute news_intel pipeline
- export execution report
"""

import sys
import os
import argparse
import logging
import traceback
import platform
from datetime import datetime


# ============================================================
# UTF-8 stdout/stderr
# ============================================================

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace",
        line_buffering=True
    )

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(
        encoding="utf-8",
        errors="replace",
        line_buffering=True
    )


# ============================================================
# Paths
# ============================================================

SCRIPT_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

HERMES_HOME = os.path.dirname(
    SCRIPT_DIR
)

MODULE_DIR = os.path.join(
    HERMES_HOME,
    "profiles",
    "outside-deepdeek",
    "skills",
    "research",
    "search-engine-v2",
    "scripts"
)

sys.path.insert(0, MODULE_DIR)


# ============================================================
# Environment
# ============================================================

os.environ["PYTHONUNBUFFERED"] = "1"

os.environ.setdefault(
    "NEWS_API_BASE",
    "http://100.107.117.23:8001"
)


# ============================================================
# Logging
# ============================================================

LOG_DIR = os.path.join(
    SCRIPT_DIR,
    "logs"
)

os.makedirs(
    LOG_DIR,
    exist_ok=True
)

LOG_FILE = os.path.join(
    LOG_DIR,
    "news-pipeline.log"
)


logger = logging.getLogger("news-pipeline")

logger.setLevel(logging.INFO)


formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
)


# file log

file_handler = logging.FileHandler(
    LOG_FILE,
    encoding="utf-8"
)

file_handler.setFormatter(
    formatter
)


# stdout log

console_handler = logging.StreamHandler(
    sys.stdout
)

console_handler.setFormatter(
    formatter
)


logger.addHandler(file_handler)
logger.addHandler(console_handler)


# ============================================================
# Exit codes
# ============================================================

EXIT_OK = 0
EXIT_PIPELINE = 1
EXIT_IMPORT = 2
EXIT_UNKNOWN = 99


# ============================================================
# Runtime info
# ============================================================

def dump_runtime():

    logger.info(
        "===== Runtime Information ====="
    )

    logger.info(
        "Python: %s",
        sys.version.replace("\n", " ")
    )

    logger.info(
        "Platform: %s",
        platform.platform()
    )

    logger.info(
        "Executable: %s",
        sys.executable
    )

    logger.info(
        "CWD: %s",
        os.getcwd()
    )

    logger.info(
        "Script Dir: %s",
        SCRIPT_DIR
    )

    logger.info(
        "Module Dir: %s",
        MODULE_DIR
    )

    logger.info(
        "NEWS_API_BASE: %s",
        os.environ.get("NEWS_API_BASE")
    )


# ============================================================
# Summary
# ============================================================

def print_summary(report):

    report = report or {}

    print()
    print("PIPELINE_RESULT")
    print(f"batch_input={report.get('batch_input',0)}")
    print(f"batch_new={report.get('batch_new',0)}")
    print(f"batch_duplicate={report.get('batch_duplicate',0)}")
    print(f"batch_tier_a={report.get('batch_tier_a',0)}")
    print(f"batch_tier_b={report.get('batch_tier_b',0)}")
    print(f"batch_tier_c={report.get('batch_tier_c',0)}")
    print(f"batch_enhanced={report.get('batch_enhanced',0)}")
    print(f"batch_pushed={report.get('batch_pushed',0)}")
    print(f"batch_push_failed={report.get('batch_push_failed',0)}")
    print(f"total_a={report.get('total_a',0)}")
    print(f"total_b={report.get('total_b',0)}")
    print(f"total_c={report.get('total_c',0)}")
    print(f"total_articles={report.get('total_articles',0)}")
    print(f"duration_pipeline={report.get('duration_pipeline_sec',0)}")
    print(f"duration_push={report.get('duration_push_sec',0)}")
    print(f"duration_total={report.get('duration_sec',0)}")
    print()


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="News Intelligence Pipeline"
    )

    parser.add_argument(
        "--hours",
        type=int,
        default=1
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=200
    )

    # 根因修复：run_pipeline() 的 do_fetch 参数默认 False，
    # 而这个 wrapper 之前从未把它暴露出来传下去，导致 Windows 计划任务
    # 触发的每一次运行都从未真正调用 batch.py 抓正文。
    # 默认设为 True，这样计划任务命令行不用改也会自动生效；
    # 想临时跳过抓正文（比如只想快速看评分结果）时传 --no-fetch。
    parser.add_argument(
        "--fetch",
        dest="fetch",
        action="store_true",
        default=True
    )

    parser.add_argument(
        "--no-fetch",
        dest="fetch",
        action="store_false"
    )

    args = parser.parse_args()


    start = datetime.now()


    try:

        logger.info(
            "========== START NEWS PIPELINE =========="
        )

        dump_runtime()


        logger.info(
            "Importing news_intel.pipeline"
        )


        try:

            from news_intel.pipeline import run_pipeline

        except Exception:

            logger.error(
                "Import failed"
            )

            logger.error(
                traceback.format_exc()
            )

            return EXIT_IMPORT



        logger.info(
            "Running pipeline hours=%s limit=%s fetch=%s",
            args.hours,
            args.limit,
            args.fetch
        )


        report = run_pipeline(
            hours=args.hours,
            limit=args.limit,
            do_fetch=args.fetch
        )


        logger.info(
            "Pipeline finished successfully"
        )


        logger.info(
            "Report=%s",
            report
        )


        print_summary(
            report
        )


        cost = (
            datetime.now()
            - start
        ).total_seconds()


        logger.info(
            "Total wrapper duration %.2fs",
            cost
        )


        logger.info(
            "========== END SUCCESS =========="
        )


        return EXIT_OK



    except Exception:

        logger.error(
            "========== PIPELINE FAILED =========="
        )

        logger.error(
            traceback.format_exc()
        )

        print(
            "PIPELINE_FAILED"
        )

        return EXIT_PIPELINE



if __name__ == "__main__":

    code = main()

    logger.info(
        "Exit code=%s",
        code
    )

    sys.exit(code)