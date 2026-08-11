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
# GLiNER 实体抽取 (v4.4.4): 回退 gliner_small-v1 (英文, 小体积)。
# 原因: gliner_multi-v2.1 (1.16GB) 对中文边界不精准/幻觉 (实测中国-伊朗文章抽成"宝马"),
# 而中文 A/B 抽取已由 extract_one 走 Qwen (更准), multi 仅对英文略优 + C级粗实体,
# 收益不抵 1.16GB 内存。multi 模型已缓存, 需要时改此行即可启用。
GLINER_MODEL = "urchade/gliner_small-v1"
GLINER_FALLBACK = "urchade/gliner_multi-v2.1"
# noThink prompt (8.5x 提速)
FACT_PROMPT = ("直接回答JSON, 禁止任何思考过程。\n你是新闻事实抽取器。只输出JSON: "
               '{"subject":"主体","action":"动作","object":"客体","location":"地点","time":"时间"}。无法确定用空字符串。')

_gliner = None  # 模块级单例


def _get_gliner():
    global _gliner
    if _gliner is None:
        from gliner import GLiNER
        for model_id in (GLINER_MODEL, GLINER_FALLBACK):
            try:
                # local_files_only: 未缓存立即失败(不联网/不挂起), 依次回退
                _gliner = GLiNER.from_pretrained(model_id, local_files_only=True)
                if model_id == GLINER_FALLBACK and GLINER_MODEL != GLINER_FALLBACK:
                    print(f"[gliner] {GLINER_MODEL} 未缓存, 回退 {GLINER_FALLBACK} (中文实体走 Qwen)")
                return _gliner
            except Exception:
                continue
        raise RuntimeError(
            f"GLiNER 加载失败 ({GLINER_MODEL} 与 {GLINER_FALLBACK} 均不可用)。"
            f"下载 multi 模型后自动启用: python -c \"from gliner import GLiNER; "
            f"GLiNER.from_pretrained('{GLINER_MODEL}')\"")
    return _gliner


def _is_cjk(text: str) -> bool:
    """是否含 CJK 汉字 (中文聚合/配额共用)。"""
    return any('一' <= ch <= '鿿' for ch in (text or ""))


def _select_with_cjk_quota(rows: list, limit: int, cjk_quota: int | None = None) -> list:
    """保证 CJK(中文) 文章占批一定比例 — 否则按 rr.id DESC 的最新 50 篇会被英文挤掉。
    published_at 混格式排序是坏的, 不能用它选中文; 显式配额最可靠。"""
    cjk_quota = cjk_quota if cjk_quota is not None else max(10, limit // 5)
    cjk = [r for r in rows if _is_cjk((r.get("title") or "") + (r.get("description") or ""))]
    non = [r for r in rows if r not in cjk]
    return cjk[:cjk_quota] + non[:max(0, limit - len(cjk[:cjk_quota]))]


def load_articles(db_path, limit):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    # v4.4.3 中文聚合: 锚点 news_intelligence + LEFT JOIN news_content;
    # 条件 content 或 description 非空 + nc.id 存在(有占位行, 保证 payload 按 id 匹配);
    # 排序 rr.id DESC (插入序=可靠时效, 替代坏掉的 published_at); Python CJK 配额。
    rows = conn.execute("""
        SELECT nc.id, ni.tier, rr.title, nc.summary_cn, rr.description, rr.published_at,
               rr.source_name, rr.article_url as url, nc.content_md as content
        FROM news_intelligence ni
        JOIN rss_raw rr ON ni.raw_id = rr.id
        LEFT JOIN news_content nc ON nc.intel_id = ni.id
        WHERE ni.tier IN ('A','B') AND nc.id IS NOT NULL
          AND ((nc.content_md IS NOT NULL AND nc.content_md != '')
               OR (rr.description IS NOT NULL AND rr.description != ''))
        ORDER BY rr.id DESC LIMIT ?
    """, (max(limit * 4, 200),)).fetchall()
    conn.close()
    return _select_with_cjk_quota(rows, limit)


def load_cjk_c_tier(db_path, limit=200):
    """C 级 CJK 文章 (GLiNER-only, 供 ner_by_article.json, 不进 Qwen/不推送)。"""
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
    rows = conn.execute("""
        SELECT nc.id, ni.tier, rr.title, nc.summary_cn, rr.description, rr.published_at,
               rr.source_name, rr.article_url as url, nc.content_md as content
        FROM news_intelligence ni
        JOIN rss_raw rr ON ni.raw_id = rr.id
        LEFT JOIN news_content nc ON nc.intel_id = ni.id
        WHERE ni.tier = 'C' AND nc.id IS NOT NULL
        ORDER BY rr.id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [r for r in rows if _is_cjk((r.get("title") or "") + (r.get("description") or ""))]


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


def extract_one(article, c_entities, qwen_allowed=True):
    """单篇: GLiNER快速路径(主体+客体锚定) → B(noThink)兜底; qwen_allowed=False 为 C 级 GLiNER-only。

    v4.4.3 中文: gliner_multi 对中文实体边界不精准(整句/幻觉主体, 实测中国-伊朗文章抽成"宝马"),
    中文文章直接用 Qwen (更准); GLiNER fast-path 仅用于英文 + C 级粗实体。
    """
    from news_intel.canonicalizer import is_media_source
    from news_intel.aggregator import _get_text
    ents = c_entities.get(article["id"], [])
    # 排除新闻来源名 (Al Jazeera 等) — 来源名是媒体自我指涉, 不是事件主体
    subj_like = [e for e in ents if e["label"] in ("person", "organization", "company")
                 and not is_media_source(e["text"])]
    obj_like = [e for e in ents if e["label"] in ("country", "city")
                and not is_media_source(e["text"])]
    gs = next((e["text"] for e in subj_like), "")
    go = next((e["text"] for e in obj_like), "")
    tl = (article.get("title") or "").lower()
    # 中文 A/B 文章: GLiNER multi 边界不精准, 直接 Qwen (B 路径更准), 不用于 grounding
    if _is_cjk(_get_text(article)):
        return _run_qwen_branch(article, [])
    # 快速路径: 主体+客体存在 且 至少一个在标题 (验证门保证准确率)
    if gs and go and (gs.lower() in tl or go.lower() in tl):
        with _STATS_LOCK:
            _STATS["A"] += 1
        return build_fact_payload(article, ents, gs, go, "", "", None)
    if not qwen_allowed:
        # C级: GLiNER-only (禁 Qwen), 即使无主体也返回 payload (fused 聚合回退 legacy action)
        with _STATS_LOCK:
            _STATS["C"] += 1
        return build_fact_payload(article, ents, gs, go, "", "", None)
    return _run_qwen_branch(article, ents)


def _run_qwen_branch(article, ents):
    """B 兜底 (Qwen noThink) — 中文优先路径; ents 用于 grounding (中文传空, 因 GLiNER 实体不精准)。"""
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

    # Phase 4 (v4.4.3 中文聚合): C 级 CJK GLiNER-only → ner_by_article.json
    # 只写 CJK 文章的 key (英文 legacy 指纹源仍是 scorer 实体, 防回归)
    ner_path = os.path.join(SCRIPT_DIR, "ner_by_article.json")
    cjk_c = load_cjk_c_tier(args.db, 200)
    if cjk_c:
        t0 = time.time()
        ner = {}
        for a in cjk_c:
            text = _get_text(a)[:512]
            ner[a["id"]] = gliner.predict_entities(
                text, ["person", "organization", "country", "city", "company", "product", "event"],
                threshold=0.35)
        with open(ner_path, "w", encoding="utf-8") as f:
            json.dump(ner, f, ensure_ascii=False)
        print(f"[ner] C级CJK {len(cjk_c)} 篇 GLiNER-only → ner_by_article.json ({time.time()-t0:.1f}s)")
    else:
        if os.path.exists(ner_path):
            os.remove(ner_path)
        print("[ner] 无 C 级 CJK, 移除旧 ner_by_article.json")


if __name__ == "__main__":
    main()
