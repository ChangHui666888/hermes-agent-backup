#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pipeline_check.py V2.1

News Intelligence Pipeline Operator

功能:

1. Pipeline 健康检查
2. 手动执行阶段
3. Agent 可执行诊断输出

Usage:

python pipeline_check.py check

python pipeline_check.py rss

python pipeline_check.py pipeline

python pipeline_check.py fetcher

python pipeline_check.py aggregator

python pipeline_check.py sync

python pipeline_check.py run
"""


import os
import sys
import json
import time
import sqlite3
import subprocess
import urllib.request
from pathlib import Path



# ============================================================
# ENVIRONMENT
# ============================================================


USER_HOME = Path.home()


# Hermes 主目录候选

HERMES_CANDIDATES = [

    USER_HOME / ".hermes",

    USER_HOME / "AppData" / "Local" / "hermes",

]


def find_hermes_home():

    current = Path(__file__).resolve()


    # 从当前脚本向上寻找 hermes
    for parent in current.parents:

        if parent.name == "hermes":

            return parent


    # fallback

    for path in HERMES_CANDIDATES:

        if path.exists():

            return path


    return HERMES_CANDIDATES[-1]



HERMES_HOME = find_hermes_home()



# scripts目录

SCRIPT_HOME = (
    HERMES_HOME /
    "scripts"
)



# search-engine-v2

SEARCH_ENGINE_HOME = (
    HERMES_HOME /
    "profiles" /
    "outside-deepdeek" /
    "skills" /
    "research" /
    "search-engine-v2" /
    "scripts"
)



# ============================================================
# DATABASE DISCOVERY
# ============================================================


RSS_DB_CANDIDATES = [

    USER_HOME /
    ".hermes" /
    "rss-archive.db",


    HERMES_HOME /
    "rss-archive.db",

]


PIPELINE_DB_CANDIDATES = [

    # 当前脚本同目录（最高优先级）
    Path(__file__).parent /
    "news_intel.db",


    # search-engine-v2/scripts/news_intel
    SEARCH_ENGINE_HOME /
    "news_intel.db",


    # 备用
    SEARCH_ENGINE_HOME /
    "news_intel" /
    "news_intel.db",

]



def find_existing(candidates):

    for db in candidates:

        if db.exists():

            return db

    return None



def get_rss_db():

    return find_existing(
        RSS_DB_CANDIDATES
    )



def get_pipeline_db():

    return find_existing(
        PIPELINE_DB_CANDIDATES
    )



# ============================================================
# CLOUD
# ============================================================


CLOUD_API = (
    os.environ.get(
        "NEWS_API_BASE",
        "http://100.107.117.23:8001"
    )
    +
    "/api/v1/dashboard"
)



# ============================================================
# COMMANDS
# ============================================================


COMMANDS = {


    "rss":

    {
        "label":"RSS",

        "cmd":[

            "python",

            str(
                SCRIPT_HOME /
                "rss-scanner.py"
            )

        ]
    },



    "pipeline":

    {
        "label":"PIPELINE",

        "cmd":[

            "python",

            str(
                SEARCH_ENGINE_HOME /
                "news-pipeline.py"
            )

        ]
    },



    "fetcher":

    {
        "label":"FETCHER",

        # 修复：batch.py 实际位于 SEARCH_ENGINE_HOME 根目录下，
        # 不在 news_intel/ 子目录里。原路径会导致
        # `python pipeline_check.py fetcher` 直接 FileNotFoundError。
        "cmd":[

            "python",

            str(
                SEARCH_ENGINE_HOME /
                "batch.py"
            )

        ]
    },



    "aggregator":

    {
        "label":"AGGREGATOR",

        "cmd":[

            "python",

            str(
                SEARCH_ENGINE_HOME /
                "test_aggregator.py"
            ),

            "--hours",
            "24",

            "--window",
            "12",

            "--limit",
            "50"

        ]
    },



    "sync":

    {
        "label":"SYNC",

        "cmd":[

            "python",

            str(
                SEARCH_ENGINE_HOME /
                "cron-sync.py"
            )

        ]
    }


}




# ============================================================
# OUTPUT
# ============================================================


def print_environment():

    print()

    print("ENVIRONMENT")

    print("-"*40)

    print(
        f"HERMES_HOME: {HERMES_HOME}"
    )

    print(
        f"RSS_DB: {get_rss_db()}"
    )

    print(
        f"PIPELINE_DB: {get_pipeline_db()}"
    )

    print(
        f"CLOUD_API: {CLOUD_API}"
    )

    print()



def success_output(
        stage,
        detail
):

    print()

    print(
        "STATUS: SUCCESS"
    )

    print(
        "PIPELINE: news-intel"
    )

    print(
        f"STAGE: {stage}"
    )

    print(
        "RESULT: PASS"
    )

    print(
        f"DETAIL: {detail}"
    )

    print(
        "NEXT: continue"
    )



def failed_output(
        stage,
        error_type,
        reason,
        impact,
        action,
        command
):

    print()

    print(
        "STATUS: FAILED"
    )

    print(
        "PIPELINE: news-intel"
    )

    print(
        f"FAILED_STAGE: {stage}"
    )

    print(
        f"ERROR_TYPE: {error_type}"
    )

    print(
        f"REASON: {reason}"
    )

    print(
        f"IMPACT: {impact}"
    )

    print(
        f"ACTION: {action}"
    )

    print(
        f"COMMAND: {command}"
    )

    print(
        "VERIFY: python pipeline_check.py check"
    )

    print(
        "STOP: true"
    )



def skipped_output(
        stage,
        reason
):

    print(
        f"CHECK {stage}: SKIPPED ({reason})"
    )



# ============================================================
# SQLITE
# ============================================================


def query_db(
        db,
        sql
):

    if db is None:

        return None


    try:

        conn = sqlite3.connect(
            str(db)
        )

        result = conn.execute(
            sql
        ).fetchone()

        conn.close()


        if result:

            return result[0]


        return 0



    except Exception as e:


        print()

        print(
            f"DB_ERROR: {db}"
        )

        print(
            f"SQL_ERROR: {e}"
        )

        print()


        return None



def table_exists(
        db,
        table
):

    if db is None:

        return False


    try:

        conn = sqlite3.connect(
            str(db)
        )


        result = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            AND name=?
            """,
            (table,)
        ).fetchone()


        conn.close()


        return result is not None


    except Exception:

        return False
        
# ============================================================
# HTTP
# ============================================================


def http_get(url):

    try:

        with urllib.request.urlopen(
            url,
            timeout=5
        ) as response:

            return json.loads(
                response.read()
            )


    except Exception as e:

        return None



# ============================================================
# CHECK RSS
# ============================================================


def check_rss():

    db = get_rss_db()


    if db is None:

        return False, (
            "RSS_DB_MISSING",
            "rss archive database not found"
        )


    if not table_exists(
        db,
        "rss_articles"
    ):

        return False, (
            "RSS_SCHEMA_MISSING",
            "rss_articles table missing"
        )



    total = query_db(
        db,
        """
        SELECT COUNT(*)
        FROM rss_articles
        """
    )


    if total is None:

        return False, (
            "RSS_DB_ERROR",
            "cannot query rss_articles"
        )


    if total > 0:

        latest = query_db(
            db,
            """
            SELECT COUNT(*)
            FROM rss_articles
            WHERE created_at >= datetime('now','-1 day')
            """
        )

        return True, (
            "",
            f"articles={total} latest24h={latest}"
        )


    return False, (
        "NO_ARTICLES",
        "rss_articles empty"
    )



# ============================================================
# CHECK PIPELINE
# ============================================================


def check_pipeline():

    db = get_pipeline_db()


    if db is None:

        return False, (
            "PIPELINE_DB_MISSING",
            "news_intel database not found"
        )


    if not table_exists(
        db,
        "news_intelligence"
    ):

        return False, (
            "PIPELINE_SCHEMA_MISSING",
            "news_intelligence missing"
        )


    total = query_db(
        db,
        """
        SELECT COUNT(*)
        FROM news_intelligence
        """
    )


    scored = query_db(
        db,
        """
        SELECT COUNT(*)
        FROM news_intelligence
        WHERE score_total IS NOT NULL
        """
    )


    if total is not None and scored == total:

        return True, (
            "",
            f"articles={total} scored={scored}"
        )


    return False, (
        "SCORER_INCOMPLETE",
        f"articles={total} scored={scored}"
    )



# ============================================================
# CHECK FETCHER
# ============================================================


def check_fetcher():

    db = get_pipeline_db()


    if db is None:

        return False, (
            "PIPELINE_DB_MISSING",
            "news_intel database missing"
        )


    if not table_exists(
        db,
        "news_content"
    ):

        return False, (
            "FETCHER_SCHEMA_MISSING",
            "news_content missing"
        )


    intel_total = query_db(
        db,
        """
        SELECT COUNT(*)
        FROM news_intelligence
        """
    )


    content_total = query_db(
        db,
        """
        SELECT COUNT(*)
        FROM news_content
        """
    )

    content_ok = query_db(
        db,
        """
        SELECT COUNT(*)
        FROM news_content
        WHERE content_md IS NOT NULL
        AND content_md!=''
        """
    )

    # True coverage: include exhausted rows in denominator.
    # content_total is an unconditional COUNT(*) — it already includes exhausted rows.
    content_exhausted = query_db(
        db,
        """
        SELECT COUNT(*)
        FROM news_content
        WHERE fetch_strategy = 'exhausted'
        """
    ) or 0

    if content_total is None or content_ok is None:

        return False, (
            "FETCHER_DB_ERROR",
            "cannot query news_content"
        )


    missing = content_total - content_ok
    # content_total already includes exhausted rows — no need to add them again
    total_accounted = content_total
    true_coverage = f"{content_ok}/{total_accounted}" if total_accounted > 0 else "0/0"
    true_pct = round(content_ok * 100 / max(total_accounted, 1), 1)


    # 没有需要抓取的数据
    if intel_total == 0:

        return False, (
            "NO_PIPELINE_DATA",
            "no articles waiting for fetch"
        )


    # 全部成功
    if missing == 0 and content_exhausted == 0:

        return True, (
            "",
            (
                f"intel={intel_total} "
                f"content={content_total} "
                f"content_ok={content_ok}"
            )
        )

    # 有 exhausted 但无 missing（exhausted 不算 missing）
    if missing == 0 and content_exhausted > 0:

        return False, (
            "FETCHER_EXHAUSTED",
            (
                f"intel={intel_total} "
                f"content={content_total} "
                f"content_ok={content_ok} "
                f"exhausted={content_exhausted} "
                f"true_coverage={true_coverage} ({true_pct}%)"
            )
        )


    # 部分或全部失败

    return False, (
        "FETCHER_EMPTY_CONTENT",
        (
            f"intel={intel_total} "
            f"content={content_total} "
            f"content_ok={content_ok} "
            f"missing={missing} "
            f"exhausted={content_exhausted} "
            f"true_coverage={true_coverage} ({true_pct}%)"
        )
    )



# ============================================================
# CHECK AGGREGATOR
# ============================================================


def check_aggregator():

    db = get_pipeline_db()


    if db is None:

        return False, (
            "PIPELINE_DB_MISSING",
            "database missing"
        )


    if not table_exists(
        db,
        "event_registry"
    ):

        return False, (
            "AGGREGATOR_SCHEMA_MISSING",
            "event_registry missing"
        )


    events = query_db(
        db,
        """
        SELECT COUNT(*)
        FROM event_registry
        """
    )


    articles = query_db(
        db,
        """
        SELECT COUNT(*)
        FROM news_intelligence
        """
    )


    if events and events > 0:


        ratio = round(
            events / articles * 100,
            2
        ) if articles else 0


        return True, (
            "",
            (
                f"events={events} "
                f"articles={articles} "
                f"ratio={ratio}%"
            )
        )


    return False, (
        "NO_EVENTS",
        "event_registry empty"
    )



# ============================================================
# CHECK SQLITE
# ============================================================


def check_sqlite():

    db = get_pipeline_db()


    if db is None:

        return False, (
            "DB_MISSING",
            "database missing"
        )


    try:

        size = (
            db.stat().st_size
            /
            1024
        )

        return True, (
            "",
            f"size={size:.0f}KB"
        )


    except Exception as e:

        return False, (
            "DB_ERROR",
            str(e)
        )



# ============================================================
# CHECK SYNC
# ============================================================


def check_sync():

    db = get_pipeline_db()


    local = query_db(
        db,
        """
        SELECT COUNT(*)
        FROM event_registry
        """
    )


    cloud = http_get(
        CLOUD_API
    )


    if cloud is None:

        return False, (
            "CLOUD_UNREACHABLE",
            "cloud api unavailable"
        )


    remote = (
        cloud
        .get(
            "metrics",
            {}
        )
        .get(
            "active_events",
            0
        )
    )


    if local == remote:

        return True, (
            "",
            f"local={local} cloud={remote}"
        )


    return False, (
        "DATA_MISMATCH",
        f"local={local} cloud={remote}"
    )



# ============================================================
# CHECK API
# ============================================================


def check_api():


    data = http_get(
        CLOUD_API
    )


    if data is None:

        return False, (
            "API_DOWN",
            "dashboard api unreachable"
        )


    events = (
        data
        .get(
            "metrics",
            {}
        )
        .get(
            "active_events",
            0
        )
    )


    return True, (
        "",
        f"active_events={events}"
    )



# ============================================================
# CHECK CHAIN
# ============================================================


CHECK_CHAIN = [

    ("RSS", check_rss),

    ("PIPELINE", check_pipeline),

    ("FETCHER", check_fetcher),

    ("AGGREGATOR", check_aggregator),

    ("SQLITE", check_sqlite),

    ("SYNC", check_sync),

    ("API", check_api)

]

# ============================================================
# CHECK COMMAND
# ============================================================


def cmd_check():

    print_environment()


    for index, (stage, checker) in enumerate(CHECK_CHAIN):

        result = checker()


        ok = result[0]


        if ok:

            print(
                f"CHECK {stage}: PASS ({result[1][1]})"
            )

            continue



        error_type = result[1][0]

        reason = result[1][1]


        print(
            f"CHECK {stage}: FAIL ({reason})"
        )


        # 后续阶段不再检查，避免误导

        for next_stage, _ in CHECK_CHAIN[index + 1:]:

            skipped_output(
                next_stage,
                f"blocked_by_{stage}"
            )


        failed_output(

            stage,

            error_type,

            reason,

            "Downstream results may be unreliable",

            (
                f"Repair {stage} stage "
                "then verify again"
            ),

            (
                f"python pipeline_check.py "
                f"{stage.lower()}"
            )

        )

        return



    success_output(

        "ALL",

        "pipeline healthy"

    )



# ============================================================
# RUN SINGLE STAGE
# ============================================================


def run_stage(name):


    if name not in COMMANDS:

        print(
            f"UNKNOWN_STAGE: {name}"
        )

        return False



    cfg = COMMANDS[name]


    label = cfg["label"]

    cmd = cfg["cmd"]


    print()

    print(
        f"RUN {label}"
    )

    print(
        "COMMAND:"
    )

    print(
        " ".join(cmd)
    )

    print()


    start = time.time()


    try:


        result = subprocess.run(

            cmd,

            cwd=str(
                SEARCH_ENGINE_HOME
            ),

            timeout=1200

        )


        elapsed = (
            time.time()
            -
            start
        )


        if result.returncode == 0:


            success_output(

                label,

                (
                    f"completed "
                    f"{elapsed:.1f}s"
                )

            )


            return True



        failed_output(

            label,

            "EXECUTION_FAILED",

            (
                f"exit_code={result.returncode}"
            ),

            (
                "Stage did not complete"
            ),

            (
                "Check stage logs"
            ),

            (
                " ".join(cmd)
            )

        )


        return False



    except subprocess.TimeoutExpired:


        failed_output(

            label,

            "TIMEOUT",

            ">1200 seconds",

            (
                "Pipeline stage blocked"
            ),

            (
                "Check process and logs"
            ),

            (
                " ".join(cmd)
            )

        )


        return False



    except Exception as e:


        failed_output(

            label,

            "EXECUTION_ERROR",

            str(e),

            (
                "Stage execution failed"
            ),

            (
                "Check environment"
            ),

            (
                " ".join(cmd)
            )

        )


        return False



# ============================================================
# FULL PIPELINE RUN
# ============================================================


def cmd_run():


    print()

    print(
        "=" * 60
    )

    print(
        "NEWS INTELLIGENCE PIPELINE RUN"
    )

    print(
        "=" * 60
    )


    stages = [

        "rss",

        "pipeline",

        "fetcher",

        "aggregator",

        "sync"

    ]


    completed = []


    for stage in stages:


        ok = run_stage(stage)


        if not ok:


            print()

            print(
                "PIPELINE STOP"
            )

            print(
                f"FAILED_STAGE: {stage}"
            )

            return



        completed.append(stage)



    print()

    print(
        "=" * 60
    )

    print(
        "PIPELINE COMPLETE"
    )

    print(
        "STAGES:"
        +
        ",".join(completed)
    )

    print(
        "=" * 60
    )


    print()


    cmd_check()



# ============================================================
# STATUS COMMAND
# ============================================================


def cmd_status():

    print_environment()


    db = get_pipeline_db()


    if db:


        print(
            "PIPELINE_DB:"
        )

        print(
            db
        )


        print(

            "EVENTS:",

            query_db(

                db,

                """
                SELECT COUNT(*)
                FROM event_registry
                """

            )

        )



# ============================================================
# MAIN
# ============================================================


def main():


    if len(sys.argv) < 2:


        print(
            __doc__
        )

        return



    command = sys.argv[1].lower()



    if command == "check":


        cmd_check()



    elif command == "run":


        cmd_run()



    elif command == "status":


        cmd_status()



    elif command in COMMANDS:


        run_stage(
            command
        )



    else:


        print(
            f"UNKNOWN COMMAND: {command}"
        )

        print(
            __doc__
        )



if __name__ == "__main__":

    main()