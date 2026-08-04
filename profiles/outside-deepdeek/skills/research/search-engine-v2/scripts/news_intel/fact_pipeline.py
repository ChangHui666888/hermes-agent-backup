#!/usr/bin/env python3
"""fact_pipeline.py — Fact Layer 生产抽取器 (混合策略, 多线程)

串联并联混合: GLiNER(串行锚定) → ThreadPool[A验证→C验证→B(noThink)兜底] → Canonicalizer → 推送

⚠️ 需系统 Python311 (有 gliner/transformers/torch) + LM Studio Qwen 在线。
用法:
  C:\\Users\\ChangHui\\AppData\\Local\\Programs\\Python\\Python311\\python.exe news_intel/fact_pipeline.py \
      --db <news_intel.db> --limit 100 --api http://100.107.117.23 --workers 3
"""

import argparse
import concurrent.futures as cf
import collections
import json
import os
import sys
import threading
import time

# 抽取统计 (2026-08-03 日志完善): 路径分布 + Qwen 耗时, 线程安全
_STATS = {"A": 0, "B": 0, "qwen_n": 0, "qwen_total_ms": 0, "qwen_max_ms": 0}
_STATS_LOCK = threading.Lock()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
sys.path.insert(0, SCRIPT_DIR)

_DEFAULT_DB = os.path.join(
    os.path.expanduser("~"),
    "AppData/Local/hermes/profiles/outside-deepdeek/skills/research/search-engine-v2/scripts/news_intel/news_intel.db",
)
QWEN_BASE = "http://127.0.0.1:1234/v1"
QWEN_MODEL = "qwen3-1.7b-instruct"
GLINER_MODEL = "urchade/gliner_small-v1"
# noThink prompt (8.5x 提速)
FACT_PROMPT = ("直接回答JSON, 禁止任何思考过程。\n你是新闻事实抽取器。只输出JSON: "
               '{"subject":"主体","action":"动作","object":"客体","location":"地点","time":"时间"}。无法确定用空字符串。')

_gliner = None  # 模块级单例


def _get_gliner():
    global _gliner
    if _gliner is None:
        from gliner import GLiNER
        _gliner = GLiNER.from_pretrained(GLINER_MODEL)
    return _gliner


def load_articles(db_path, limit):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    rows = conn.execute("""
        SELECT nc.id, rr.title, nc.summary_cn, rr.description, rr.published_at, rr.source_name,
               rr.article_url as url, nc.content_md as content
        FROM news_content nc
        JOIN news_intelligence ni ON nc.intel_id = ni.id
        JOIN rss_raw rr ON ni.raw_id = rr.id
        WHERE ni.tier IN ('A','B') AND nc.content_md IS NOT NULL AND nc.content_md != ''
        ORDER BY rr.published_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows


def qwen_fact(article):
    """B: Qwen noThink Raw Fact"""
    import httpx
    from news_intel.aggregator import _get_text
    title = (article.get("title") or "")[:300]
    summary = _get_text(article)[:400]  # 输入一致性: 与 legacy 指纹同一统一文本
    try:
        r = httpx.post(f"{QWEN_BASE}/chat/completions",
                       json={"model": QWEN_MODEL,
                             "messages": [{"role": "user", "content": f"{FACT_PROMPT}\n\n标题: {title}\n摘要: {summary}"}],
                             "max_tokens": 300}, timeout=60)
        c = (r.json()["choices"][0]["message"].get("content") or "").strip()
        s, e = c.find("{"), c.rfind("}")
        if s == -1 or e == -1:
            return {}
        return {k: str(json.loads(c[s:e + 1]).get(k, "")).strip() for k in ("subject", "action", "object", "location", "time")}
    except Exception:
        return {}


def build_fact_payload(article, c_entities, subject, object_, action_text, location, time_):
    """Canonicalizer → fact + fact_entity payload"""
    from news_intel.canonicalizer import canonicalize_action, resolve_entity, split_entities

    def ground(name, ents):
        low = (name or "").lower()
        best = None
        for e in ents:
            en = e["text"].lower()
            if en and (en in low or low in en):
                if best is None or len(e["text"]) > len(best["text"]):
                    best = e
        return best

    def entities_payload(name_str, ents, role):
        from news_intel.canonicalizer import is_media_source
        out = []
        for p in split_entities(name_str):
            if is_media_source(p):
                continue  # 排除新闻来源名当主体 (Al Jazeera→US 误判)
            g = ground(p, ents)
            ent = resolve_entity(p, g["label"] if g else "")
            if ent["id"]:
                out.append({"entity_id": ent["id"], "entity_name": ent["name"],
                            "entity_type": ent["type"], "role": role})
        return out

    title_text = article.get("title", "")
    act = canonicalize_action(action_text, object_, title_text)
    ents = entities_payload(subject, c_entities, "SUBJECT") + entities_payload(object_, c_entities, "OBJECT")
    return {
        "article_id": article["id"],
        "article_url": article.get("url") or "",
        "action_type": act["type"],
        "action_event_type": act["event_type"],
        "action_detail": (action_text or "")[:200],
        "event_time": time_,  # 端点 _clean_time 清洗非时间戳
        "location": location,
        "confidence": None,
        "evidence_type": "Told",
        "entities": ents,
    }


def extract_one(article, c_entities):
    """单篇: GLiNER快速路径(主体+客体锚定) → B(noThink)兜底"""
    from news_intel.canonicalizer import is_media_source
    ents = c_entities.get(article["id"], [])
    # 排除新闻来源名 (Al Jazeera 等) — 来源名是媒体自我指涉, 不是事件主体
    subj_like = [e for e in ents if e["label"] in ("person", "organization", "company")
                 and not is_media_source(e["text"])]
    obj_like = [e for e in ents if e["label"] in ("country", "city")
                and not is_media_source(e["text"])]
    gs = next((e["text"] for e in subj_like), "")
    go = next((e["text"] for e in obj_like), "")
    tl = (article.get("title") or "").lower()
    # 快速路径: 主体+客体存在 且 至少一个在标题 (验证门保证准确率)
    if gs and go and (gs.lower() in tl or go.lower() in tl):
        with _STATS_LOCK:
            _STATS["A"] += 1
        return build_fact_payload(article, ents, gs, go, "", "", None)
    # B 兜底 (Qwen)
    _tq = time.monotonic()
    b_raw = qwen_fact(article)
    _ms = int((time.monotonic() - _tq) * 1000)
    with _STATS_LOCK:
        _STATS["B"] += 1
        _STATS["qwen_n"] += 1
        _STATS["qwen_total_ms"] += _ms
        _STATS["qwen_max_ms"] = max(_STATS["qwen_max_ms"], _ms)
    return build_fact_payload(article, ents, b_raw.get("subject", ""), b_raw.get("object", ""),
                              b_raw.get("action", ""), b_raw.get("location", ""), b_raw.get("time") or None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=_DEFAULT_DB)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--api", default="http://100.107.117.23")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--verbose", "-v", action="store_true", help="打印每篇抽取明细")
    args = ap.parse_args()

    articles = load_articles(args.db, args.limit)
    print(f"[load] {len(articles)} 篇")

    # Phase 1: GLiNER 串行 (避免 torch 并发)
    t0 = time.time()
    gliner = _get_gliner()
    c_entities = {}
    from news_intel.aggregator import _get_text
    for a in articles:
        text = _get_text(a)[:512]  # 输入一致性: 与 legacy 指纹同一统一文本 (title+description+content)
        c_entities[a["id"]] = gliner.predict_entities(text, ["person", "organization", "country", "city", "company", "product", "event"], threshold=0.35)
    print(f"[GLiNER] 串行完成 {time.time()-t0:.1f}s")

    # Phase 2: 多线程抽取 (A/C 快 + B noThink)
    t0 = time.time()
    payloads = []
    done_n = 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(extract_one, a, c_entities): a for a in articles}
        for f in cf.as_completed(futures):
            payloads.append(f.result())
            done_n += 1
            if done_n % 10 == 0 or done_n == len(articles):
                print(f"[extract] {done_n}/{len(articles)} 篇 ({time.time()-t0:.0f}s)", flush=True)
    print(f"[extract] 多线程完成 {time.time()-t0:.1f}s (workers={args.workers})")

    if args.verbose:
        print("\n── 抽取明细 (verbose) ──")
        for p in payloads:
            print(f"  art={p['article_id']} action={p['action_type']}({p['action_event_type']}) "
                  f"loc={p['location'] or '-'} | entities={[(e['entity_id'], e['role']) for e in p['entities'][:3]]}")

    # Phase 3: 推送 /internal/facts/batch
    import httpx
    token = os.environ.get("NEWS_API_TOKEN", "v8-pipeline-token-2026-xK9mP2sR7wQ")
    with httpx.Client(timeout=60, mounts={"all://": httpx.HTTPTransport(proxy=None)}) as client:
        r = client.post(f"{args.api}/internal/facts/batch", json=payloads,
                        headers={"X-Internal-Token": token})
    print(f"[push] {args.api}/internal/facts/batch → {r.status_code} {r.text[:100]}")

    # 保存 payload 副本
    with open(os.path.join(SCRIPT_DIR, "fact_pipeline_payload.json"), "w", encoding="utf-8") as f:
        json.dump(payloads, f, ensure_ascii=False, indent=2)
    print(f"[save] payload {len(payloads)} 条 → fact_pipeline_payload.json")

    # 质量摘要 (2026-08-03 日志完善): 末尾输出, 落在 auto-pipeline 捕获的最后400字符内
    n = len(payloads)
    others = sum(1 for p in payloads if p.get("action_type") == "OTHER")
    grounded = sum(1 for p in payloads if any(e.get("role") == "SUBJECT" and e.get("entity_name") for e in p.get("entities", [])))
    with _STATS_LOCK:
        s = dict(_STATS)
    qwen_avg = s["qwen_total_ms"] // max(s["qwen_n"], 1)
    dist = collections.Counter(p["action_type"] for p in payloads)
    print(f"[stats] 路径: A快={s['A']} B(Qwen)={s['B']} | Qwen {s['qwen_n']}次 avg={qwen_avg}ms max={s['qwen_max_ms']}ms")
    print(f"[stats] 质量: OTHER={others}({others*100//max(n,1)}%) 主体落地={grounded}/{n} | 动作={dict(dist.most_common(6))}")


if __name__ == "__main__":
    main()
