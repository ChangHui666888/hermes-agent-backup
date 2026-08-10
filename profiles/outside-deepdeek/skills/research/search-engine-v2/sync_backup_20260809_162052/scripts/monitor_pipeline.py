#!/usr/bin/env python3
"""monitor_pipeline.py — 流水线监控指标采集 (2026-08-08)

解析本地数据源，输出结构化监控指标 JSON，供监控看板/告警规则使用。

数据源:
  - ~/.hermes/rss-scanner-report.json    采集
  - 生产 profile scripts/pipeline.log    各步骤 (最新一轮)
  - 生产 profile scripts/news_intel/news_intel.db  评分/事件

用法:
  python scripts/monitor_pipeline.py              # 输出监控指标 JSON
  python scripts/monitor_pipeline.py --quiet      # 只输出指标值行 (轻量)

指标设计见 Wiki: 04-config/monitoring.md
"""
import json
import os
import re
import sys
from datetime import datetime

# ── 路径 ──
HOME = os.path.expanduser("~")
PROD = os.path.expanduser(
    "~/AppData/Local/hermes/profiles/outside-deepdeek/skills/research/search-engine-v2/scripts")
SCANNER_REPORT = os.path.join(HOME, ".hermes", "rss-scanner-report.json")
PIPELINE_LOG = os.path.join(PROD, "pipeline.log")
NEWS_DB = os.path.join(PROD, "news_intel", "news_intel.db")
HISTORY_FILE = os.path.join(HOME, ".hermes", "monitor-history.jsonl")   # 时序历史 (每轮追加)


def _snapshot_delta() -> dict:
    """DB 关键计数增量 (vs 上次历史记录) + 追加富快照到时序历史。"""
    import sqlite3
    db_counts = {}
    try:
        conn = sqlite3.connect(NEWS_DB)
        db_counts["events_total"] = conn.execute("SELECT count(*) FROM event_registry").fetchone()[0]
        db_counts["articles_scored"] = conn.execute("SELECT count(*) FROM news_intelligence").fetchone()[0]
        tier = {r[0]: r[1] for r in conn.execute("SELECT tier, count(*) FROM news_intelligence GROUP BY tier").fetchall()}
        db_counts["tier_a"] = tier.get("A", 0)
        db_counts["tier_b"] = tier.get("B", 0)
        db_counts["tier_c"] = tier.get("C", 0)
        # 评分分维度 (五维均分, 监控"某维score骤降")
        dims = conn.execute(
            "SELECT round(avg(score_source),1), round(avg(score_impact),1), round(avg(score_entity),1), "
            "round(avg(score_market),1), round(avg(score_velocity),1) FROM news_intelligence").fetchone()
        db_counts["score_dims"] = {
            "source": dims[0], "impact": dims[1], "entity": dims[2],
            "market": dims[3], "velocity": dims[4],
        }
        conn.close()
    except Exception:
        return {}
    # 评分耗时 (pipeline.log Sync 步骤)
    try:
        _steps = metrics_pipeline().get("steps") or {}
        db_counts["score_sec"] = next((v for k, v in _steps.items() if "Sync" in k), None)
    except Exception:
        pass
    prev = None
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                lines = [l for l in f.read().strip().splitlines() if l.strip()]
            if lines:
                prev = json.loads(lines[-1])
        except Exception:
            pass
    delta = dict(db_counts)
    if prev:
        delta["events_delta"] = db_counts["events_total"] - prev.get("events_total", db_counts["events_total"])
        delta["articles_delta"] = db_counts["articles_scored"] - prev.get("articles_scored", db_counts["articles_scored"])
    else:
        delta["events_delta"] = delta["articles_delta"] = None
    # 追加富快照 (时序, 供趋势图)
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(), **db_counts}) + "\n")
    except Exception:
        pass
    return delta


def metrics_scanner() -> dict:
    """采集指标 (rss-scanner-report.json)。"""
    try:
        with open(SCANNER_REPORT, encoding="utf-8") as f:
            d = json.load(f)
        due = d.get("feeds_due") or d.get("feeds_active") or 1
        return {
            "feeds_total": d.get("feeds_total"),
            "feeds_active": d.get("feeds_active"),
            "feeds_quarantined": d.get("feeds_quarantined"),
            "feeds_due": d.get("feeds_due"),
            "feeds_ok": d.get("feeds_ok"),
            "feeds_error": d.get("feeds_error"),
            "feeds_unchanged": d.get("feeds_unchanged"),
            "success_rate": round((d.get("feeds_ok", 0) / due) * 100, 1) if due else 0,
            "articles_new": d.get("articles_new"),
            "articles_total": d.get("articles_total"),
            "duration_sec": d.get("duration_sec"),
            "errors": (d.get("errors") or [])[:10],
        }
    except Exception as e:
        return {"error": f"scanner report: {e}"}


_LOG_TAIL_BYTES = 150_000  # 只读尾部 150KB (含最近 1-2 轮), 轻量不拖累


def _read_log_tail(path: str, max_bytes: int = _LOG_TAIL_BYTES) -> str:
    """只读日志尾部 (避免整文件读取, 日志随轮次增长)。"""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
            tail = f.read().decode("utf-8", errors="replace")
            # 丢弃不完整首行
            nl = tail.find("\n")
            return tail[nl + 1:] if nl >= 0 else tail
        return f.read().decode("utf-8", errors="replace")


def _latest_run_segments(log_text: str) -> list:
    """切出最新一轮 DONE 的日志段 (按 ===== 分隔)。"""
    blocks = re.split(r"={10,}", log_text)
    return [b for b in blocks if "DONE in" in b]


def _step_timings(seg: str) -> dict:
    """各步骤耗时 (瓶颈层): 解析 Step 时间戳 → 相邻步间隔秒。"""
    steps = re.findall(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*Step\s*([\d.]+)/[\d.]+:\s*([^\n]+)", seg)
    done = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*DONE in", seg)
    import datetime as _dt
    times = []
    for ts, num, name in steps:
        try:
            t = _dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            times.append((num, name.strip()[:20], t))
        except Exception:
            pass
    if done:
        try:
            times.append(("DONE", "DONE", _dt.datetime.strptime(done.group(1), "%Y-%m-%d %H:%M:%S")))
        except Exception:
            pass
    out = {}
    for i, (num, name, t) in enumerate(times):
        if i + 1 < len(times):
            out[f"{num} {name}"] = max(0, int((times[i + 1][2] - t).total_seconds()))
    return out


def metrics_pipeline() -> dict:
    """各步骤指标 (pipeline.log 最新一轮, 只读尾部)。"""
    if not os.path.exists(PIPELINE_LOG):
        return {"error": "pipeline.log 缺失"}
    log = _read_log_tail(PIPELINE_LOG)
    blocks = _latest_run_segments(log)
    if not blocks:
        return {"error": "pipeline.log 无完整运行段"}
    seg = blocks[-1]  # 最新一轮
    m = {}
    m["steps"] = _step_timings(seg)
    # 总耗时
    done = re.search(r"DONE in (\d+)s", seg)
    m["total_duration_sec"] = int(done.group(1)) if done else None
    # Fact
    fact = re.search(r"FACT_45:.*?(\d+)\s*ok,\s*(\d+)\s*fail", seg)
    if fact:
        m["fact_ok"], m["fact_fail"] = int(fact.group(1)), int(fact.group(2))
    else:
        m["fact_ok"] = m["fact_fail"] = None
    fact_pct = re.search(r"FACT_45:.*?\s(\d+)/\d+ 篇", seg)
    m["fact_pct"] = int(fact_pct.group(1)) if fact_pct else None
    qwen = re.search(r"Qwen (\d+)次 avg=(\d+)ms max=(\d+)ms", seg)
    if qwen:
        m["qwen_count"], m["qwen_avg_ms"], m["qwen_max_ms"] = int(qwen.group(1)), int(qwen.group(2)), int(qwen.group(3))
    other = re.search(r"OTHER=(\d+)\((\d+)%\)", seg)
    if other:
        m["fact_other_pct"] = int(other.group(2))
    landing = re.search(r"主体落地=(\d+)/(\d+)", seg)
    if landing:
        m["subject_landing"] = round(int(landing.group(1)) / max(int(landing.group(2)), 1) * 100, 1)
    # 聚合 (含输入量 unassigned/facts, 用于区分"无输入"vs"聚合失败")
    agg = re.search(r"AGGREGATE:\s*(\d+)\s*ok,\s*(\d+)\s*fail.*?(\d+)\s*unassigned articles,\s*(\d+)\s*facts,\s*(\d+)\s*marked", seg)
    if agg:
        m["agg_ok"], m["agg_fail"] = int(agg.group(1)), int(agg.group(2))
        m["unassigned"], m["facts_in"], m["marked"] = int(agg.group(3)), int(agg.group(4)), int(agg.group(5))
    else:
        agg2 = re.search(r"AGGREGATE:\s*(\d+)\s*ok,\s*(\d+)\s*fail.*?(\d+)\s*marked", seg)
        if agg2:
            m["agg_ok"], m["agg_fail"], m["marked"] = int(agg2.group(1)), int(agg2.group(2)), int(agg2.group(3))
    # 归一
    norm = re.search(r"NORMALIZE:.*?(\d+)\s*groups merged, (\d+) deleted", seg)
    if norm:
        m["norm_merged"], m["norm_deleted"] = int(norm.group(1)), int(norm.group(2))
    # 推送
    cs = re.search(r"CLOUD_SYNC:\s*(\d+)\s*ok,\s*(\d+)\s*fail", seg)
    if cs:
        m["cloud_sync_ok"], m["cloud_sync_fail"] = int(cs.group(1)), int(cs.group(2))
    cp = re.search(r"CONTENT_PUSH:\s*(\d+)\s*ok,\s*(\d+)\s*fail", seg)
    if cp:
        m["content_push_ok"], m["content_push_fail"] = int(cp.group(1)), int(cp.group(2))
    m["pipeline_done"] = bool(done)
    return m


def metrics_scoring() -> dict:
    """评分/事件指标 (news_intel.db)。"""
    try:
        import sqlite3
        conn = sqlite3.connect(NEWS_DB)
        total = conn.execute("SELECT count(*) FROM news_intelligence").fetchone()[0]
        tier = {r[0]: r[1] for r in conn.execute(
            "SELECT tier, count(*) FROM news_intelligence GROUP BY tier").fetchall()}
        avg = conn.execute("SELECT round(avg(score_total),1) FROM news_intelligence").fetchone()[0]
        cats = {r[0]: r[1] for r in conn.execute(
            "SELECT category, count(*) FROM news_intelligence WHERE category IS NOT NULL GROUP BY category ORDER BY 2 DESC LIMIT 8").fetchall()}
        ev = conn.execute("SELECT count(*) FROM event_registry").fetchone()[0]
        conn.close()
        return {
            "articles_scored": total, "tier": tier, "avg_score": avg,
            "top_categories": cats, "events_local": ev,
        }
    except Exception as e:
        return {"error": f"news_intel.db: {e}"}


def push_to_vps(out: dict) -> int:
    """推送指标到 VPS /internal/monitor (配置中心展示)。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # scripts/
        from config.env import INTERNAL_TOKEN
        import httpx
        api = os.environ.get("NEWS_API_BASE", "http://100.107.117.23") + "/internal/monitor"
        r = httpx.post(api, json=out, headers={"X-Internal-Token": INTERNAL_TOKEN}, timeout=15)
        return r.status_code
    except Exception as e:
        print(f"[push] 失败: {e}")
        return 0


def main(quiet=False, push=False):
    delta = _snapshot_delta()
    out = {
        "timestamp": datetime.now().isoformat(),
        "采集": metrics_scanner(),
        "流水线": metrics_pipeline(),
        "评分": metrics_scoring(),
        "变化": delta,
    }
    if push:
        code = push_to_vps(out)
        print(f"[push] VPS /internal/monitor → {code}")
    if quiet:
        # 轻量输出: 关键行
        c, p, s = out["采集"], out["流水线"], out["评分"]
        print(f"采集成功率={c.get('success_rate')}% 隔离={c.get('feeds_quarantined')} 新增={c.get('articles_new')} 扫描{c.get('duration_sec')}s")
        print(f"Fact={p.get('fact_ok')}/{p.get('fact_pct')} OTHER={p.get('fact_other_pct')}% 落地={p.get('subject_landing')}% Qwen={p.get('qwen_avg_ms')}ms")
        print(f"聚合marked={p.get('marked')} 推送={p.get('cloud_sync_ok')}ok/{p.get('cloud_sync_fail')}fail 总耗时={p.get('total_duration_sec')}s DONE={p.get('pipeline_done')}")
        print(f"评分文章={s.get('articles_scored')} 平均={s.get('avg_score')} Tier={s.get('tier')}")
        return
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(quiet="--quiet" in sys.argv, push="--push" in sys.argv)
