# News Intelligence Platform — 生产流水线 (Actual Running State)

> 基于代码实际运行状态更新。2026-07-13

## 实际运行架构

```
═══════════════════════════════════════════════════════════════════
  Sentinel Intelligence — 七层流水线 (实际运行)
═══════════════════════════════════════════════════════════════════

  L0  RSS采集 ──→ L1 五维评分 ──→ L2 全文抓取 ──→ L3 结构抽取
  L4 三级增强 ──→ L5 事件聚合 ──→ L6 云端同步 ──→ L7 Web展示

  ←────── 规则引擎 (零LLM) ──────→  ← LLM可选 →  ← 规则 ──→
═══════════════════════════════════════════════════════════════════
```

## L0 — RSS 采集

```
RSS Scanner (外部独立进程, Hermes cron 30min)
  │ 46 RSS + 18 Nitter + 6 Chinese Official = 70 源
  │ feedparser → SOCKS5 代理 (境外) / 直连 (国内)
  │
  ▼
rss-archive.db (~/.hermes/rss-archive.db)
  │ 2,404 篇文章
  │ 字段: source, title, summary, link, category, date

🚫 LLM: 无
```

## L1 — 五维评分

```
sync.py (sync_recent)
  │ 读取 rss-archive.db → 去重 (已评分链接跳过)
  │
  ▼
scorer.py (score_article)
  │ Source(0-20):  source_scores.json 查表 (Reuters=20, BBC=16, unknown=5)
  │ Impact(0-30):  event_keywords.json 关键词匹配 (战争=30, 财报=15)
  │ Entity(0-20):  entity_weights.json 实体权重 (Federal Reserve=20)
  │ Market(0-20):  asset_graph.json 市场关联 (NVDA→半导体=18)
  │ Velocity(0-10): Jaccard 指纹比对 ±30min 窗口
  │
  ▼
news_intel.db (三表)
  ├── rss_raw          (2,404 rows): title, description, url, source_name, published_at
  ├── news_intelligence (2,404 rows): score_total, tier(A/B/C), entities(JSON), categories
  └── news_content      (211 rows): content_md, summary_cn, fetch_strategy

🚫 LLM: 无 (纯查表 + 正则)
```

## L2 — 全文抓取

```
pipeline.py --fetch (仅 Tier A/B)
  │
  ▼
batch.py (ThreadPoolExecutor × 4)
  │
  ▼
fetchers.py (4 级级联, 成功即停)
  │ ① httpx + trafilatura        (cost=1) ← 大多数源
  │ ② web.archive.org            (cost=1) ← 付费墙绕过
  │ ③ Scrapling StealthyFetcher  (cost=2) ← Cloudflare
  │ ④ Playwright headless        (cost=3) ← JS渲染

🚫 LLM: 无
```

## L3 — 脚本结构化抽取

```
core/extractor.py
  │ 标题 → Markdown H1
  │ 日期 → URL路径 / ISO / "Published" / 中文日期 / 兜底
  │ 作者 → "By/Author" 正则
  │ 摘要 → 前2-3语义句
  │ 要点 → 信号词+数字+实体 加权 Top5, 0.78ms/篇

🚫 LLM: 无
```

## L4 — 三级增强

```
路由: score ≥ 90 → Tier A | 60-89 → Tier B | <60 → Tier C

Tier C (<60): enhance_python()
  规则标签 + 实体合并 + 前2句摘要

Tier B (60-89): enhance_qwen()
  → Qwen3-1.7B 本地 (LM Studio :1234)
  标签 + 实体(含 organization) + 动作 + 事件提示 + 中文20字摘要
  不可用 → 自动降级 Python

Tier A (≥90): enhance_deepseek()
  → DeepSeek V4 Flash (api.deepseek.com)
  事件概括 + 市场影响(bullish/bearish) + 风险(low-high) + 未来关注点
  无 API Key → 自动降级 Python

已增强跳过: LEFT JOIN nc WHERE nc.id IS NULL
```

## L5 — 事件聚合 (核心)

```
aggregator.py v4.4 (纯规则, 0.1s/批次)

Step 1 — build_fingerprint(article)
  subject: companies/persons 中 entity_weight 最大 (hub ×0.3, ≥0.15)
  action:  14 类动作枚举 → 计数排序 (ATTACKS/DIES/SUES/NEGOTIATES...)
  object:  countries/companies 中加权最高 (排除 subject)
  topic:   12 类关键词词典 (Legal/Military/Diplomacy/Economic...)
  country: entities.countries[0] canonicalized

Step 2 — fingerprint_score(fp1, fp2)
  location mismatch → 0 (硬拒绝)
  anchor exact match → 100
  action(25) + subject(10-25) + object(10-30) + topic(10) + type(10) + participants(5-10)
  EVENT_THRESHOLD=50, MERGE_THRESHOLD=75

Step 3 — cluster + output
  → 21-field Event Dossier
  → event_registry INSERT
  → source_registry UPSERT
  → entity_registry UPSERT

当前: 41 events, 19 sources, 18 entities
🚫 LLM: 无
```

## L6 — 云端同步

```
cron-sync.py (Hermes cron, 30min, job: 92b78fee7369)
  │ ① aggregate_events() 重新聚合
  │ ② SCP news_intel.db → cloud:/home/administrator/news-intel-web/data/
  │ ③ docker compose restart backend

云端 Docker
  │ sqlite3.connect("file:/data/news_intel.db?mode=ro&immutable=1", uri=True)
  │ FastAPI → 6 API endpoints

🚫 LLM: 无
```

## L7 — Web 展示

```
Nginx (:80)
  │ /     → Next.js → Dashboard   (Global Situation + Map + Heat + Feed)
  │ /events/[id] → Event Detail  (Facts → Evidence → Evolution → Flow)
  │ /events     → Event Explorer (Table + Filters + Pagination)
  │ /map        → Geo Monitor    (520px Map)
  │ /sources    → Source Network (Authority Grid)
  │ /search     → Search         (Debounce)
  │
  └─ /api/* → FastAPI (:8000)

http://100.107.117.23
🚫 LLM: 无
```

## LLM 使用总览

| 层 | 环节 | LLM | 触发 | 实际状态 |
|:--:|------|:--:|------|:--:|
| L0 | RSS 采集 | 🚫 | — | 外部进程 |
| L1 | 五维评分 | 🚫 | — | 同步运行 |
| L2 | 全文抓取 | 🚫 | — | 按需 |
| L3 | 结构抽取 | 🚫 | — | 按需 |
| L4 | 增强 | 🤖 Qwen3/DeepSeek | Tier A/B | 可选, 失败降级 Python |
| L5 | **事件聚合** | 🚫 | — | **运行中** |
| L6 | 云端同步 | 🚫 | — | cron 30min |
| L7 | Web 展示 | 🚫 | — | Docker 持续 |

## 当前数据量

```
rss_raw:           2,404 篇
news_intelligence: 2,404 篇 (100% 评分)
news_content:      211 篇 (8.8% 全文抓取)
event_registry:    41 事件
source_registry:   19 来源
entity_registry:   18 实体
```

## 自动化覆盖

| 任务 | 方式 | 频率 | 状态 |
|------|------|:--:|:--:|
| RSS 扫描 | Hermes cron (外部) | 30min | ✅ |
| 评分 + 入库 | sync.py → scorer.py | 管道内 | ✅ |
| 聚合 | aggregator.py | cron-sync 触发 | ✅ |
| 云端同步 | cron-sync.py | 30min | ✅ |
| Web 服务 | Docker Compose | 持续 | ✅ |
