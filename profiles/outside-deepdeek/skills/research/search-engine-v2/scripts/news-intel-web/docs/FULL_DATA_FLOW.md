# Data Flow: RSS → Web

```
═══════════════════════════════════════════════════════════════════
PHASE 0 — CRON TRIGGER (每 30 分钟)
═══════════════════════════════════════════════════════════════════

  Hermes Cron
  ├── rss-scan      扫描 70 个 RSS 源 → rss-archive.db
  └── db-cloud-sync  聚合 + SCP 推送 + 重启云端容器


═══════════════════════════════════════════════════════════════════
PHASE 1 — DATA INGESTION (RSS Scanner)
═══════════════════════════════════════════════════════════════════

  46 RSS + 18 Nitter + 6 Chinese Official
    │
    ▼
  feedparser → rss-archive.db
    │           ┌─────────────────────────┐
    │           │ source, title, summary,  │
    │           │ link, category, date     │
    │           └─────────────────────────┘
    │
    ▼
  sync.py
    │  读取 rss-archive.db 最近 2h 数据
    │
    ▼
  scorer.py (五维评分)
    │  source(20) + impact(30) + entity(20) + market(20) + velocity(10) = 0~100
    │  → tier: A(>90) / B(60-90) / C(<60)
    │
    ▼
  news_intel.db
    ├── rss_raw          (原始 RSS: title, description, url, published_at...)
    ├── news_intelligence (评分: score_total, tier, entities, categories...)
    └── news_content      (正文: content_md, summary_cn, fetch_strategy...)


═══════════════════════════════════════════════════════════════════
PHASE 2 — CONTENT FETCH (batch.py)
═══════════════════════════════════════════════════════════════════

  pipeline.py --fetch
    │  选取 Tier A/B 文章 URL
    │
    ▼
  batch.py
    │  ThreadPoolExecutor(4)
    │
    ▼
  fetchers.py (4 级级联)
    │  ① httpx + trafilatura         (cost=1)
    │  ② web.archive.org             (cost=1)
    │  ③ Scrapling StealthyFetcher   (cost=2)
    │  ④ Playwright headless         (cost=3)
    │
    ▼
  news_content 表填充
    │  content_md, summary_cn, fetch_strategy, fetch_cost


═══════════════════════════════════════════════════════════════════
PHASE 3 — EVENT AGGREGATION (aggregator.py v4.4)
═══════════════════════════════════════════════════════════════════

  articles (from 3-table JOIN: rss_raw + news_intelligence + news_content)
    │
    ▼
  build_fingerprint(article)
    │  subject (entity weight, hub ×0.3, ≥0.15)
    │  action  (14-class count-sort: ATTACKS, DIES, SUES, NEGOTIATES...)
    │  object  (entity weight, hub ×0.3)
    │  topic   (12-class keyword: Military, Legal, Diplomatic, Economic...)
    │  country (entities.countries[0])
    │  participants (set)
    │
    ▼
  fingerprint_score(fp1, fp2)
    │  location mismatch → 0 (hard reject)
    │  anchor exact match → 100
    │  action(25) + subject(10-25) + object(10-30) + topic(10) + type(10)
    │  EVENT_THRESHOLD=50 → event
    │  MERGE_THRESHOLD=75 → strong merge
    │
    ▼
  cluster() → 21-field Event Object
    │
    ▼
  写入 event_registry (SQLite)
    │  event_id, title, summary, SAO, source, actors
    │  evidence[quote+source+url], source_chain[break/follow]
    │  timeline[time+update], confidence, stage, keywords...
    │
    ├── source_registry   (source_id, name, type, authority)
    └── entity_registry   (entity_id, canonical_name, type)


═══════════════════════════════════════════════════════════════════
PHASE 4 — CLOUD SYNC (cron-sync.py, 每 30 分钟)
═══════════════════════════════════════════════════════════════════

  cron-sync.py
    │  ① aggregate_events() — 重新聚合
    │  ② SCP news_intel.db → 100.107.117.23:/home/administrator/news-intel-web/data/
    │  ③ SSH docker compose restart backend
    │
    ▼
  云端 Docker
    │  volume mount: ./data/news_intel.db → /data/news_intel.db (read-only)
    │  docker compose restart → 重新连接新 DB 文件


═══════════════════════════════════════════════════════════════════
PHASE 5 — API LAYER (FastAPI, 云端)
═══════════════════════════════════════════════════════════════════

  FastAPI (main.py)
    │  sqlite3.connect("file:/data/news_intel.db?mode=ro&immutable=1", uri=True)
    │
    ├── GET /api/v1/dashboard     → metrics + hot_events + map_events
    ├── GET /api/v1/events        → 分页列表 + topic/stage/country 筛选
    ├── GET /api/v1/events/{id}   → 完整 Event Dossier
    ├── GET /api/v1/sources       → source_registry + event_count
    ├── GET /api/v1/search?q=     → LIKE title/summary/keywords
    └── GET /api/v1/map/events    → country 非空的 event 标记


═══════════════════════════════════════════════════════════════════
PHASE 6 — FRONTEND (Next.js 16, 云端)
═══════════════════════════════════════════════════════════════════

  Nginx (:80)
    │
    ├── /       → Next.js (:3000) → Dashboard
    │              │  fetch(/api/v1/dashboard) → Situation → Map → Heat → Feed
    │
    ├── /events/[id] → Event Detail
    │              │  fetch(/api/v1/events/{id}) → Facts → Evidence → Evolution → Flow
    │
    ├── /events → Event Explorer
    │              │  fetch(/api/v1/events?filters) → Table + Pagination
    │
    ├── /map   → Geo Monitor
    │              │  fetch(/api/v1/map/events) → WorldMap 520px
    │
    ├── /sources → Source Network
    │              │  fetch(/api/v1/sources) → Authority Grid
    │
    ├── /search → Search
    │              │  fetch(/api/v1/search?q=...) → Results
    │
    └── /api/* → Nginx proxy_pass → FastAPI (:8000)


═══════════════════════════════════════════════════════════════════
PHASE 7 — USER
═══════════════════════════════════════════════════════════════════

  http://100.107.117.23
    │
    ▼
  浏览器渲染 Sentinel Intelligence Dashboard
```

## 自动化矩阵

| 步骤 | 触发 | 频率 | LLM |
|------|------|:--:|:--:|
| RSS 扫描 | Hermes Cron rss-scan | 30min | ❌ |
| 评分 | sync.py → scorer.py | 30min | ❌ |
| 抓取 | pipeline.py → batch.py | 按需 | ❌ |
| 聚合 | aggregator.py | 30min | ❌ |
| 云端同步 | cron-sync.py | 30min | ❌ |
| API 服务 | FastAPI | 持续 | ❌ |
| 前端渲染 | Next.js | 浏览器 | ❌ |

**全链路零 LLM 依赖。确定性规则 + SQLite，无人值守运行。**
