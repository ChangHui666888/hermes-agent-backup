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
QWEN_MODEL = "qwen3-1.7b-instruct"          # 中文 (中文精度高)
GEMMA_MODEL = "gemma-4-e2b-it"              # 英文 (P1 路由: 英文精度 > Qwen, Object +29pp, ISS-20260810-012)
MODEL_MAX_CONCURRENCY = 3                   # P1 (ISS-20260810-012): 每个模型最大 3 并发
_QWEN_SEM = None
_GEMMA_SEM = None


def _sem(model):
    """按模型取信号量 (每个模型 ≤ MODEL_MAX_CONCURRENCY 并发, 防 LM Studio 单模型过载)。"""
    global _QWEN_SEM, _GEMMA_SEM
    if model == GEMMA_MODEL:
        if _GEMMA_SEM is None:
            _GEMMA_SEM = threading.BoundedSemaphore(MODEL_MAX_CONCURRENCY)
        return _GEMMA_SEM
    if _QWEN_SEM is None:
        _QWEN_SEM = threading.BoundedSemaphore(MODEL_MAX_CONCURRENCY)
    return _QWEN_SEM
# GLiNER 实体抽取 (v4.4.4): 回退 gliner_small-v1 (英文, 小体积)。
# 原因: gliner_multi-v2.1 (1.16GB) 对中文边界不精准/幻觉 (实测中国-伊朗文章抽成"宝马"),
# 而中文 A/B 抽取已由 extract_one 走 Qwen (更准), multi 仅对英文略优 + C级粗实体,
# 收益不抵 1.16GB 内存。multi 模型已缓存, 需要时改此行即可启用。
GLINER_MODEL = "urchade/gliner_small-v1"
GLINER_FALLBACK = "urchade/gliner_multi-v2.1"
# noThink prompt (8.5x 提速) — P0 Schema V2 (ISS-20260810-012): facts[] + action{verb,status,polarity} + evidence_type
FACT_PROMPT = ("直接回答JSON, 禁止任何思考过程。\n你是新闻事实抽取器。一篇文章可含多条事实。只输出JSON: "
               '{"facts":[{"subject":"主体","action":{"verb":"动作动词","status":"COMPLETED/ONGOING/PLANNED/EXPECTED/CONSIDERED/DELAYED/CANCELLED/DENIED/ATTEMPTED/ANNOUNCED/UNKNOWN",'
               '"polarity":"POSITIVE/NEGATIVE/NEUTRAL/UNKNOWN"},"object":"客体","location":"地点","time":"时间",'
               '"confidence":0-1,"evidence":"支持原句",'
               '"evidence_type":"DIRECT/OFFICIAL/DOCUMENT/STATEMENT/REPORT/SOURCE_CLAIM/ANALYSIS/OPINION/RUMOR/UNKNOWN"}]}。'
               '最多3条事实; 若客体是数值/金额/日期/短语($0.22、81st anniversary)则 object 置空字符串; '
               'evidence_type 无法确定必须 UNKNOWN, 不得推断; 无法确定用空字符串; 只输出JSON。')

_EVIDENCE_ENUM = {"DIRECT", "OFFICIAL", "DOCUMENT", "STATEMENT", "REPORT", "SOURCE_CLAIM",
                  "ANALYSIS", "OPINION", "RUMOR", "UNKNOWN"}

# P1 批量抽取 (ISS-20260810-012): results[] 紧凑输出 — 2B 模型吞吐受输出token约束, 批量比分开快 2.7x (833 vs 2372 tok)
_BATCH_PROMPT_ZH = ("你是新闻事实抽取器。对下面每篇文章**分别**抽取事实, 每篇最多2条, 只含这些字段:\n"
                    '{"article_id":"<id>","facts":[{"subject":"主体","action":{"verb":"动作动词","status":"UNKNOWN","polarity":"NEUTRAL"},"object":"客体"}]}\n'
                    '整体只输出: {"results":[{"article_id":"...","facts":[...]}]}\n'
                    '无法确定用空字符串; 只输出JSON。')
_BATCH_PROMPT_EN = ("You are a news fact extractor. For each article below, extract facts separately, at most 2 per article, ONLY these fields:\n"
                    '{"article_id":"<id>","facts":[{"subject":"subject","action":{"verb":"action verb","status":"UNKNOWN","polarity":"NEUTRAL"},"object":"object"}]}\n'
                    'Output only: {"results":[{"article_id":"...","facts":[...]}]}\n'
                    'Use empty string if unsure. Output only JSON.')

# Gemma 全英文 prompt (P1 路由: 英文文章用英文 prompt 精度更高)
FACT_PROMPT_EN = ("Answer directly in JSON, do NOT think aloud. You are a news fact extractor. An article may contain "
                  'multiple facts. Output only JSON: '
                  '{"facts":[{"subject":"subject","action":{"verb":"action verb",'
                  '"status":"COMPLETED/ONGOING/PLANNED/EXPECTED/CONSIDERED/DELAYED/CANCELLED/DENIED/ATTEMPTED/ANNOUNCED/UNKNOWN",'
                  '"polarity":"POSITIVE/NEGATIVE/NEUTRAL/UNKNOWN"},"object":"object","location":"location","time":"time",'
                  '"confidence":0-1,"evidence":"supporting sentence",'
                  '"evidence_type":"DIRECT/OFFICIAL/DOCUMENT/STATEMENT/REPORT/SOURCE_CLAIM/ANALYSIS/OPINION/RUMOR/UNKNOWN"}]}. '
                  'At most 3 facts. If the object is a value/amount/date/phrase ($0.22, 81st anniversary), set object to empty string. '
                  'If unsure, use empty string. Output only JSON.')

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
    """模型路由 Raw Facts (P1, ISS-20260810-012): CJK→Qwen(中文prompt), 英文→Gemma(英文prompt)。

    Schema V2: facts[] + action{verb,status,polarity} + confidence/evidence。
    返回 list[dict]: [{subject, action, action_status, action_polarity, object, location, time,
                        confidence, evidence}, ...] (最多 3 条, 可 0 条)。
    """
    import httpx
    from news_intel.aggregator import _get_text
    title = (article.get("title") or "")[:300]
    summary = _get_text(article)[:400]  # 输入一致性: 与 legacy 指纹同一统一文本
    _cjk = _is_cjk(title + " " + summary)
    model = QWEN_MODEL if _cjk else GEMMA_MODEL
    prompt = FACT_PROMPT if _cjk else FACT_PROMPT_EN
    labels = ("标题", "摘要") if _cjk else ("Title", "Summary")
    # P1-1 Context B (ISS-20260810-012): 标题 + 摘要 + 正文前4段 (A/B 实验 +2~11pp, 尤其 Object)
    content = article.get("content") or article.get("content_md") or ""
    if content:
        paras = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 30][:4]
        if paras:
            body_label = "正文" if _cjk else "Body"
            summary += f"\n{body_label}: " + "\n".join(paras[:4])[:800]
    # P1 (ISS-20260810-012): max_tokens 1500 保证 facts[]+SAO 不截断; 每模型并发 ≤ MODEL_MAX_CONCURRENCY
    with _sem(model):
        try:
            r = httpx.post(f"{QWEN_BASE}/chat/completions",
                           json={"model": model,
                                 "messages": [{"role": "user", "content": f"{prompt}\n\n{labels[0]}: {title}\n{labels[1]}: {summary}"}],
                                 "max_tokens": 1500}, timeout=120)
            c = (r.json()["choices"][0]["message"].get("content") or "").strip()
        except Exception:
            return []
    s, e = c.find("{"), c.rfind("}")
    if s == -1 or e == -1:
        return []
    try:
        raw = json.loads(c[s:e + 1])
    except Exception:
        return []

    def _norm(f):
        act = f.get("action") if isinstance(f, dict) else None
        if isinstance(act, dict):
            verb, st, pol = act.get("verb", ""), act.get("status", ""), act.get("polarity", "")
        else:
            verb, st, pol = (act or ""), "", ""
        return {
            "subject": str(f.get("subject", "")).strip(),
            "action": str(verb).strip(),
            "action_status": str(st).strip(),
            "action_polarity": str(pol).strip(),
            "object": str(f.get("object", "")).strip(),
            "location": str(f.get("location", "")).strip(),
            "time": str(f.get("time", "")).strip(),
            "confidence": f.get("confidence"),
            "evidence": str(f.get("evidence", "")).strip(),
        }

    facts = raw.get("facts")
    if isinstance(facts, list):
        return [_norm(f) for f in facts[:3] if isinstance(f, dict)]
    # 旧格式单条 → 包装成 list (兼容)
    return [_norm(raw)]


def _batch_call(chunk, model, prompt, labels):
    """一次批量请求 (results[] 紧凑), 每模型信号量。返回 {article_id(int): [fact_raw,...]}"""
    import httpx
    art_lines = []
    for a in chunk:
        summ = (a.get("summary_cn") or a.get("description") or "")[:400]
        art_lines.append(f'[{a["id"]}] {labels[0]}: {a.get("title", "")} | {labels[1]}: {summ}')
    text = "\n".join(art_lines)
    with _sem(model):
        try:
            r = httpx.post(f"{QWEN_BASE}/chat/completions",
                           json={"model": model, "messages": [{"role": "user", "content": f"{prompt}\n\n{text}"}],
                                 "max_tokens": 2500}, timeout=240)
            c = (r.json()["choices"][0]["message"].get("content") or "").strip()
        except Exception:
            return {}
    s = c.find("{")
    if s == -1:
        return {}
    try:
        raw, _ = json.JSONDecoder().raw_decode(c[s:])
    except Exception:
        return {}
    out = {}
    for it in (raw.get("results") or []):
        aid = it.get("article_id", "")
        try:
            key = int(str(aid).strip().strip('"'))
        except Exception:
            key = str(aid)
        facts = []
        for f in (it.get("facts") or [])[:3]:
            if not isinstance(f, dict):
                continue
            act = f.get("action")
            verb, st, pol = ((act.get("verb", ""), act.get("status", ""), act.get("polarity", ""))
                             if isinstance(act, dict) else (act or "", "", ""))
            facts.append({"subject": str(f.get("subject", "")).strip(), "action": str(verb).strip(),
                          "action_status": str(st).strip(), "action_polarity": str(pol).strip(),
                          "object": str(f.get("object", "")).strip(), "location": "", "time": "",
                          "confidence": None, "evidence": "", "evidence_type": ""})
        if key not in (None, ""):
            out[key] = facts
    return out


def extract_batch(articles, chunk_size=8):
    """批量抽取 (P1, ISS-20260810-012): 每 chunk 一次请求, results[] 紧凑输出, 语言分流(CJK→Qwen/Gemma)。

    2B 模型吞吐受输出token约束 — 批量 results[] 比分开快 ~2.7x (833 vs 2372 tok)。
    articles: [{id, title, description, summary_cn, ...}]
    返回 {article_id(int): [fact_raw, ...]} (fact_raw 喂 build_fact_payload)。
    """
    zh = [a for a in articles if _is_cjk((a.get("title") or "") + (a.get("description") or ""))]
    en = [a for a in articles if a not in zh]
    chunks = []
    for grp, model, prompt, labels in ((zh, QWEN_MODEL, _BATCH_PROMPT_ZH, ("标题", "摘要")),
                                       (en, GEMMA_MODEL, _BATCH_PROMPT_EN, ("Title", "Summary"))):
        for i in range(0, len(grp), chunk_size):
            chunks.append((grp[i:i + chunk_size], model, prompt, labels))
    results = {}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for _out in ex.map(lambda ch: _batch_call(*ch), chunks):
            for aid, fs in _out.items():
                results[aid] = fs
    return results


def build_fact_payload(article, c_entities, fact_raw):
    """一条原始 fact (Qwen 或 GLiNER) → 结构化 Fact Schema V2 记录 (ISS-20260810-012)。

    fact_raw: {subject, action, action_status, action_polarity, object, location, time, confidence, evidence}
    返回(平铺一条 = batch 一个元素, 聚合按 article_id 归组):
      {article_id, article_url, subject, action{type,status,polarity,verb}, object,
       time{raw,value}, location{name,entity_id,type}, confidence, evidence,
       action_type, action_event_type, action_detail, action_status, action_polarity,
       event_time, location_str, entities[]}
    """
    from news_intel.canonicalizer import (canonicalize_action, resolve_entity,
                                          split_entities, is_media_source, _is_value_phrase, infer_object_type)

    def ground(name, ents):
        low = (name or "").lower()
        best = None
        for e in ents:
            en = e["text"].lower()
            if en and (en in low or low in en):
                if best is None or len(e["text"]) > len(best["text"]):
                    best = e
        return best

    def entity_obj(name):
        """主体/客体 → {name, entity_id, type}; 值/短语 → entity_id None + type Other (P0 门控)。"""
        name = (name or "").strip()
        if not name or _is_value_phrase(name):
            return {"name": name, "entity_id": None, "type": "Other"}
        for p in split_entities(name):
            if is_media_source(p):
                continue
            g = ground(p, c_entities)
            ent = resolve_entity(p, g["label"] if g else "")
            if ent.get("name"):
                return {"name": ent["name"], "entity_id": ent.get("id") or None,
                        "type": ent.get("type") or "Other"}
        return {"name": name, "entity_id": None, "type": "Other"}

    def entity_list(name, role):
        out = []
        for p in split_entities(name):
            if is_media_source(p):
                continue  # 排除新闻来源名当主体 (Al Jazeera→US 误判)
            g = ground(p, c_entities)
            ent = resolve_entity(p, g["label"] if g else "")
            if ent.get("id"):  # 门控后: 值/短语 id 为空 → 跳过, 不再生成 ENT_ 垃圾
                out.append({"entity_id": ent["id"], "entity_name": ent["name"],
                            "entity_type": ent["type"], "role": role})
        return out

    subj = entity_obj(fact_raw.get("subject", ""))
    obj = entity_obj(fact_raw.get("object", ""))
    subj["object_type"] = "ENTITY" if subj.get("entity_id") else "UNKNOWN"
    obj["object_type"] = infer_object_type(obj["name"], obj)
    act = canonicalize_action(fact_raw.get("action", ""), obj["name"],
                              article.get("title", ""),
                              fact_raw.get("action_status", ""), fact_raw.get("action_polarity", ""))
    ents = entity_list(fact_raw.get("subject", ""), "SUBJECT") + \
           entity_list(fact_raw.get("object", ""), "OBJECT")
    et = str(fact_raw.get("evidence_type", "") or "").strip().upper()
    if et not in _EVIDENCE_ENUM:
        et = "UNKNOWN"  # 契约: 无法确定必须 UNKNOWN, 不得推断
    return {
        "article_id": article["id"],
        "article_url": article.get("url") or "",
        # Schema V2 结构化
        "subject": subj,
        "action": {"type": act["type"], "status": act["status"],
                   "polarity": act["polarity"], "verb": act["verb"]},
        "object": obj,
        "time": {"raw": fact_raw.get("time", "") or None, "value": None},
        "location": {"name": fact_raw.get("location", "") or None, "entity_id": None, "type": None},
        "confidence": fact_raw.get("confidence"),
        "evidence": fact_raw.get("evidence", ""),
        "evidence_type": et,
        # 平铺兼容 (聚合/后端沿用)
        "action_type": act["type"],
        "action_event_type": act["event_type"],
        "action_detail": act["verb"],
        "action_status": act["status"],
        "action_polarity": act["polarity"],
        "event_time": fact_raw.get("time"),
        "location_str": fact_raw.get("location", ""),
        "entities": ents,
    }


def extract_one(article, c_entities, qwen_allowed=True):
    """单篇 → facts[] (Schema V2, 可 0 条)。GLiNER快速路径 → B(noThink) 多事实; qwen_allowed=False 为 C 级。

    v4.4.3 中文: gliner_multi 对中文实体边界不精准(整句/幻觉主体), 中文文章直接用 Qwen。
    P0 (ISS-20260810-012): 返回 facts **列表**(可空); A/C 快路径无动作的 fact 交由 fact_validator REJECT。
    """
    from news_intel.canonicalizer import is_media_source
    from news_intel.aggregator import _get_text

    # P0 Gate 2 (ISS-20260810-012): Event Relevance — 非事件文章(综述/分析/解读/观点) → facts=[]
    from news_intel.fact_eligibility import is_event
    if not is_event(article):
        return []

    def _gl_blank_fact(gs, go):
        return {"subject": gs, "object": go, "action": "", "action_status": "", "action_polarity": "",
                "location": "", "time": "", "confidence": None, "evidence": "", "evidence_type": ""}

    ents = c_entities.get(article["id"], [])
    subj_like = [e for e in ents if e["label"] in ("person", "organization", "company")
                 and not is_media_source(e["text"])]
    obj_like = [e for e in ents if e["label"] in ("country", "city")
                and not is_media_source(e["text"])]
    gs = next((e["text"] for e in subj_like), "")
    go = next((e["text"] for e in obj_like), "")
    tl = (article.get("title") or "").lower()
    # 中文 A/B: GLiNER multi 边界不精准, 直接 Qwen (B 路径更准)
    if _is_cjk(_get_text(article)):
        return _run_qwen_branch(article, [])
    # 快速路径: 主体+客体存在 且 至少一个在标题 (无动作 → validator REJECT, 见契约门禁)
    if gs and go and (gs.lower() in tl or go.lower() in tl):
        with _STATS_LOCK:
            _STATS["A"] += 1
        return [build_fact_payload(article, ents, _gl_blank_fact(gs, go))]
    if not qwen_allowed:
        # C级: P0 接口冻结 — P1 由 RuleFactEngine 完整实现; 现 GLiNER-only 兜底 (无动作 → validator REJECT)
        with _STATS_LOCK:
            _STATS["C"] += 1
        return [build_fact_payload(article, ents, _gl_blank_fact(gs, go))]
    return _run_qwen_branch(article, ents)


class RuleFactEngine:
    """C-tier Rule Fact Engine — **P0 冻结接口, P1 完整实现** (Dictionary + Regex + Action/Entity/Industry/Market Map)。

    A/B(AI Fact) 与 C(Rule Fact) 输出**完全同 Schema V2**(契约 §5)。
    """
    def extract(self, article: dict) -> list:
        """→ facts[] (Schema V2)"""
        raise NotImplementedError


def _run_qwen_branch(article, ents):
    """B 兜底 (Qwen noThink 多事实) — 中文优先路径; 返回 facts[] (可 0 条)。"""
    _tq = time.monotonic()
    raw_facts = qwen_fact(article)
    _ms = int((time.monotonic() - _tq) * 1000)
    with _STATS_LOCK:
        _STATS["B"] += 1
        _STATS["qwen_n"] += 1
        _STATS["qwen_total_ms"] += _ms
        _STATS["qwen_max_ms"] = max(_STATS["qwen_max_ms"], _ms)
    return [build_fact_payload(article, ents, rf) for rf in raw_facts]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=_DEFAULT_DB)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--api", default="http://100.107.117.23")
    ap.add_argument("--workers", type=int, default=6)  # P1: 两模型各 ≤3 并发 → 池 6
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
            res = f.result()
            # P0: extract_one 返回 facts 列表, 扁平化 (一篇文章可多条 fact)
            payloads.extend(res if isinstance(res, list) else [res])
            done_n += 1
            if done_n % 10 == 0 or done_n == len(articles):
                print(f"[extract] {done_n}/{len(articles)} 篇 ({time.time()-t0:.0f}s)", flush=True)
    print(f"[extract] 多线程完成 {time.time()-t0:.1f}s (workers={args.workers}) · facts={len(payloads)}")

    # P0 (ISS-20260810-012): 写 news_intelligence.facts_json (Schema V2 facts[] per article)
    try:
        from news_intel.db import init_db as _idb, get_db as _gdb, update_article_facts
        _idb()
        _wdb = _gdb()
        _by_art = {}
        for p in payloads:
            _by_art.setdefault(p["article_id"], []).append(p)
        for _aid, _fs in _by_art.items():
            update_article_facts(_wdb, _aid, json.dumps(_fs, ensure_ascii=False))
        _wdb.close()
        print(f"[save] news_intelligence.facts_json 写入 {len(_by_art)} 篇文章")
    except Exception as e:
        print(f"[save] facts_json 写入失败(非致命): {e}")

    # A/B 事件 (2026-08-10, ISS-20260810-012): 提取 facts → validator → aggregate_ab → 落库
    try:
        from news_intel.fact_validator import validate_facts
        from news_intel.event_ab import aggregate_ab
        from news_intel.db import init_db as _ab_idb, get_db as _ab_gdb, save_ab_events
        _v = validate_facts(payloads)
        _passed = [r["repaired"] if r["verdict"] == "REPAIR" else f
                   for f, r in zip(payloads, _v) if r["verdict"] != "REJECT"]
        _abf = [{"subject_id": (f.get("subject") or {}).get("entity_id") or (f.get("subject") or {}).get("name"),
                 "subject_name": (f.get("subject") or {}).get("name", ""),
                 "action_type": (f.get("action") or {}).get("type", "OTHER"),
                 "object_id": (f.get("object") or {}).get("entity_id") or (f.get("object") or {}).get("name"),
                 "object_name": (f.get("object") or {}).get("name", "")} for f in _passed]
        _ab = aggregate_ab(_abf)
        _bid = {}
        for _b in _ab["b_events"]:
            for _aid in _b["a_event_ids"]:
                _bid[_aid] = _b["id"]
        for _a in _ab["a_events"]:
            _a["b_event_id"] = _bid.get(_a["id"], "")
        _sn = {}
        for _a in _ab["a_events"]:
            _sn.setdefault(_a["subject_id"], _a["subject_name"])
        for _b in _ab["b_events"]:
            _b["subject_name"] = _sn.get(_b["subject_id"], "")
        _ab_idb()
        _wdb2 = _ab_gdb()
        save_ab_events(_wdb2, _ab["a_events"], _ab["b_events"])
        _wdb2.close()
        # 推送到 VPS (web 展示用)
        import httpx as _httpx
        _token = os.environ.get("NEWS_API_TOKEN", "v8-pipeline-token-2026-xK9mP2sR7wQ")
        with _httpx.Client(timeout=30, mounts={"all://": _httpx.HTTPTransport(proxy=None)}) as _cl:
            _r = _cl.post(f"{args.api}/internal/ab-events",
                          json={"a_events": _ab["a_events"], "b_events": _ab["b_events"]},
                          headers={"X-Internal-Token": _token})
        print(f"[ab] A事件={len(_ab['a_events'])} B事件={len(_ab['b_events'])} 落库+推送VPS({_r.status_code}) (facts={len(_passed)})")
    except Exception as e:
        print(f"[ab] A/B 落库/推送失败(非致命): {e}")

    if args.verbose:
        print("\n── 抽取明细 (verbose) ──")
        for p in payloads:
            print(f"  art={p['article_id']} action={p['action_type']}({p['action_event_type']}) "
                  f"S={p['subject'].get('name')} O={p['object'].get('name')} "
                  f"entities={[(e['entity_id'], e['role']) for e in p['entities'][:3]]}")

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
