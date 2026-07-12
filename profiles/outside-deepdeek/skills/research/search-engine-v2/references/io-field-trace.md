# 各阶段输入/输出字段完整追踪 (v4.4)

> 从 RSS 扫描到 24字段 Event Dossier + 云端推送 的完整字段流。
> 所有字段名均可从代码中找到赋值语句。

---

## Phase 0: Cron Trigger → (无数据流)

Hermes cron 每30min触发，本身不产生数据。

---

## Phase 1: RSS Scanner → rss-archive.db

**输出表**: `rss_articles` (外部数据库, `~/.hermes/rss-archive.db`)
**读取代码**: `news_intel/sync.py:31-37`

| 字段 | 类型 | 来源 |
|------|------|------|
| source | TEXT | RSS feed 名称 |
| title | TEXT | feedparser entry.title |
| summary | TEXT | feedparser entry.summary (HTML stripped) |
| link | TEXT | feedparser entry.link → 唯一键 |
| category | TEXT | RSS feed 原生分类标签 |
| date | TEXT | feedparser entry.published_parsed |

**→ sync_recent() 读取**: `source, title, summary, link, category, date`

---

## Phase 1.1: sync.py + scorer.py → news_intel.db

**读取**: rss-archive.db → score_article() → 写入三表

### score_article() 输出 (`news_intel/scorer.py:247-263`)

| 字段 | 区间 | 评分逻辑 |
|------|:--:|------|
| total | 0–100 | 五维: source+impact+entity+market+velocity |
| source | 0–20 | source_scores.json 查表 |
| impact | 0–30 | event_keywords.json 正则命中 |
| entity | 0–20 | entity_weights.json 实体权重 |
| market | 0–20 | asset_graph.json 市场关联 |
| velocity | 0–10 | Jaccard 0.5 + 30min窗口 |
| tier | A/B/C | >90=A, 60-90=B, <60=C |
| categories | list | 关键词命中的分类 |
| entities | dict | {companies, persons, countries} |
| market_assets | list | 匹配到的资产/股票代码 |
| velocity_count | int | 同事件报道数 |

### 写入三表 (`news_intel/db.py`)

**rss_raw** (18字段): guid, source_name, source_domain, article_url, title, description, published_at, category_raw, ...

**news_intelligence** (14字段): raw_id, score_total, score_source, score_impact, score_entity, score_market, score_velocity, tier, category, tags(JSON), entities(JSON), velocity_count, scored_at

**news_content** (19字段, Phase 2填充): intel_id, article_url, content_md, content_len, fetch_strategy, fetch_cost, summary_cn, summary_en, key_points(JSON), source_headline, published_at, author_name, extraction_method, llm_model, llm_cost, temporal_check(JSON)

---

## Phase 2: batch.py + core/fetchers.py (全文抓取)

**独立运行** · 零 Agent · `python batch.py --urls urls.txt --out results.jsonl`

### 输入
| 输入 | 来源 |
|------|------|
| URL 列表 | 文件 / stdin / pipeline.py |
| `--llm-extract` (可选) | CLI 标志 → DeepSeek 结构化抽取 |
| `DEEPSEEK_API_KEY` | 环境变量 (仅 --llm-extract) |

### extract_url() 输出 (`batch.py:50-155`)

| 字段 | 类型 | 说明 |
|------|------|------|
| ok | bool | 是否成功获取有效正文 |
| url | str | 原始输入URL |
| domain | str | get_profile(url) 提取 |
| content | str | Markdown 正文 (trafilatura/readability-lxml) |
| strategy_used | str | direct\|archive\|google_cache\|scrapling\|browser |
| total_cost | int | 成本总和: direct=1, archive=1, scrapling=2, browser=3 |
| cost_trace | list | 每个尝试策略的 {strategy, cost, ok, error?, content_len?} |
| structured | dict | {headline, subheadline, author, published_at, summary, key_points} |
| temporal_check | dict | {freshness_mode, risk, warnings[], score} |

**失败时**:
| error | str | "所有策略均失败" / "内容为空/过短" |
| strategies_tried | list | 实际尝试过的策略名称 |

### 写入 news_content (`news_intel/db.py:196-245`)

batch结果 → upsert_content(): content_md, content_len, fetch_strategy, fetch_cost, summary_cn, summary_en, key_points, source_headline, published_at, author_name, extraction_method, llm_model, llm_cost, temporal_check

---

## Phase 3: aggregator.py v4.4 (事件聚合 · 零LLM + 持久化)

### 📥 输入 (test_aggregator.py 跨三表 JOIN, `test_aggregator.py:27-38`)

| 字段 | 来自表 | 聚合中使用 |
|------|--------|-----------|
| id | news_content | article_ids 追溯 |
| title | rss_raw | _detect_action() 动作检测 → 计数排序 |
| summary_cn | news_content | _classify_topics() → summary 拼接 |
| description | rss_raw | _get_text() 全文检索 |
| score_total | news_intelligence | 排序 (高分优先作为 centroid) |
| tier | news_intelligence | 参考 |
| entities | news_intelligence | build_fingerprint Subject/Object (JSON) |
| published_at | rss_raw | 时间窗过滤 + stage 计算 |
| source_name | rss_raw | source.primary_source + sources[] |

### 内部: build_fingerprint() (`aggregator.py:248-305`)

| 字段 | 类型 | 生成逻辑 |
|------|------|---------|
| subject | str | companies/persons 中 entity_weight 最大 (hub×0.3, ≥0.15) |
| subject_weight | float | global_IDF × topic_IDF × entity_type_weight |
| action | str | 14类枚举 → 计数排序取最多 |
| object | str | countries/companies 加权最高 (不含subject, hub×0.3) |
| object_weight | float | 同 subject_weight |
| event_type | str | ACTION_MAP[action][0] |
| primary_topic | str | TOPIC_SIGNALS 命中最多 |
| secondary_topic | str | TOPIC_SIGNALS 命中次多 |
| country | str\|None | entities.countries[0] canonicalized |
| participants | frozenset | _extract_participants() |
| anchor | str | {subject}\|{action}\|{object}\|{primary} |

### 内部: fingerprint_score() (`aggregator.py:308-354`)

| 维度 | 分数 | 条件 |
|------|:--:|------|
| location 硬约束 | return 0 | 不同 country → 直接拒绝 |
| anchor 快速通道 | return 100 | SAO+Topic 完全相同 |
| Action | +25 | 同动作类型 (非OTHER) |
| Subject | +10~25 | 同名 + 稀有度加权 |
| Object | +10~30 | 同名 + 稀有度加权 |
| Topic | +10/+5 | primary相同=10, secondary=5 |
| Event Type | +10 | 同 event_type |
| Participants | +5~10 | ≥2个国家重叠=10, 1个=5 |

**阈值**: EVENT_THRESHOLD=50, MERGE_THRESHOLD=75

### 📤 输出: 21字段 Event Object (`aggregator.py:583-603`)

| 字段 | 类型 | 生成逻辑 |
|------|------|---------|
| event_id | str | EVT-{YYYYMMDD}-{idx+1:03d} |
| subject{name,type} | obj | centroid + _known_entity_types |
| action{type,detail} | obj | centroid + _extract_action_detail() |
| object{name,type} | obj | centroid + _known_entity_types |
| event_type | str | centroid |
| event_time | str\|null | ev.start_time.isoformat() |
| location{country,region} | obj | fingerprint.country + region(null) |
| source{primary,authority,count,sources[]} | obj | first_article + max权威度 + 去重 |
| doc_refs[{url,title}] | list | 前5篇 |
| actors[{entity,type,role}] | list | _infer_actor_roles() |
| title | str | ev.best_title |
| summary | str | 前3篇 summary_cn 拼接 (HTML过滤) |
| keywords | list | ev.topics 聚合 |
| confidence | float | 0.4×auth + 0.3×coherence + 0.2×diversity + 0.1×volume |
| coherence | float | 成员间平均 pairwise 相似度 |
| extraction_method | str | "v4.3-saeo" |
| related_entities[{name,type}] | list | 前20 entity_refs |
| article_count | int | len(ev.article_ids) |
| article_ids | list[int] | DB主键 |
| stage | str | <2h=breaking, 2-24h=developing, 24h-7d=active, 7-30d=stable, >30d=closed |
| first_seen | str\|null | ev.start_time.isoformat() |
| last_updated | str\|null | ev.last_time.isoformat() |

---

## Phase 4: enhancers.py (三级增强)

### Tier C (<60分 · 零依赖)

**输入**: title, description, entities, categories
**输出** (`enhancers.py:22-45`): tags[], entities{companies,persons,countries}, summary_cn, summary_en, category, method:"python", llm_model:null, llm_cost:0

### Tier B (60-90分 · ⚠️ QWEN_API_KEY)

**输入**: title + description (前600字符)
**输出** (`enhancers.py:166-200`): tags[], entities{companies,persons,countries,organizations}, actions[], event_hint, summary_cn(≤20字), category, method:"qwen3", llm_model:"qwen3-1.7b", llm_cost:0

### Tier A (>90分 · ⚠️ DEEPSEEK_API_KEY)

**输入**: title + description + content_md (前3000字符)
**输出** (`enhancers.py:242-320`): event, impact, companies[], assets[], market_signal, risk_level, future_watch, confidence(0-1), tags[], entities{}, summary_cn, summary_en, method:"deepseek-flash", llm_model:"deepseek-v4-flash", llm_cost
| extraction_method | str | "v4.4-saeo" |
| related_entities[{entity_id,name,type}] | list | 前20 entity_refs + entity_id |
| article_count | int | len(ev.article_ids) |
| article_ids | list[int] | DB主键 |
| stage | str | <2h=breaking, 2-24h=developing, 24h-7d=active, 7-30d=stable, >30d=closed |
| first_seen | str\|null | ev.start_time.isoformat() |
| last_updated | str\|null | ev.last_time.isoformat() |
| **evidence** [{quote,source,url}] | list | 🆕 v4.4: 前5篇 description 摘录 |
| **source_chain** [{source_id,source_name,time,role,url}] | list | 🆕 v4.4: break/follow 链 |
| **timeline** [{time,update,source}] | list | 🆕 v4.4: 按小时去重的关键节点 |

→ **自动持久化**: event_registry + source_registry + entity_registry

---

## Phase 3.5: Event Registry (🆕 v4.4 · 自动)

**写入**: aggregate_events() → `upsert_event()` → event_registry 表
**注册**: `upsert_source()` → source_registry, `upsert_entity()` → entity_registry

---

## Phase 5.3: Event Push (🆕 v4.4)

**输入**: event dict (24字段) 或 event_registry 中的事件
**输出** (`pusher.py:82-112`): `push_events()` → POST `{NEWS_API_BASE}/internal/events/batch`
28字段: event_id, title, summary, event_type, stage, confidence, coherence,
  subject(JSON), action(JSON), object(JSON), location_country,
  primary_source, primary_source_id, source_authority, source_count, sources(JSON),
  article_count, article_ids(JSON), doc_refs(JSON),
  actors(JSON), keywords(JSON), related_entities(JSON),
  evidence(JSON), source_chain(JSON), timeline(JSON),
  llm_analysis(JSON), event_time, first_seen, last_updated, extraction_method

---

## 关键数据流速查 (v4.4)

```
rss-archive.db → score_article() → news_intel.db 三表
    → batch.py → 正文 → news_content
    → 三表JOIN → build_fingerprint → cluster → merge
    → 24字段 Event Dossier (v4.4: +evidence +source_chain +timeline)
    → 自动持久化: event_registry + source_registry + entity_registry
    → 可选: generate_intel() event-level LLM 分析
    → 可选: push_events() → POST /internal/events/batch → 云端 PostgreSQL
```
    → 21字段 Event Object
    → 可选: enhancer (3 tier) + generator (insight)
    → pusher.py → POST /internal/news/batch
```
