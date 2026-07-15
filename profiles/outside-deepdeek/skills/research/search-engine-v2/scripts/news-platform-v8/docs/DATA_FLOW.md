# News Intelligence Platform — Data Flow (Frozen)

## End-to-End

```
┌─────────────────────────────────────────────────────────┐
│ WINDOWS 11 · HERMES AGENT                               │
│                                                         │
│  70 RSS feeds ──→ RSS Scanner ──→ rss-archive.db        │
│       (cron 30min)                                      │
│                          │                              │
│                          ▼                              │
│                   sync.py + scorer.py                    │
│                   (5-dim: source/impact/entity/          │
│                    market/velocity → tier A/B/C)         │
│                          │                              │
│                          ▼                              │
│                   news_intel.db (3 tables)              │
│                   rss_raw · news_intelligence            │
│                   · news_content                        │
│                          │                              │
│                          ▼                              │
│                   batch.py + fetchers.py                 │
│                   (httpx/trafilatura/Scrapling/          │
│                    Playwright → full text)               │
│                          │                              │
│                          ▼                              │
│                   aggregator.py v4.4                     │
│                   build_fingerprint → cluster            │
│                   → 21-field Event Object                │
│                          │                              │
│                          ▼                              │
│              ┌──────────────────────┐                   │
│              │  Event Registry      │                   │
│              │  event_registry      │                   │
│              │  source_registry     │ ← SQLite file      │
│              │  entity_registry     │                   │
│              └──────────┬───────────┘                   │
│                         │                               │
└─────────────────────────┼───────────────────────────────┘
                          │
                          │ file path:
                          │ .../news_intel/news_intel.db
                          │
┌─────────────────────────┼───────────────────────────────┐
│ CLOUD VPS · DOCKER      │                               │
│                         ▼                               │
│              FastAPI Read Adapter                        │
│              opens SQLite in read-only mode              │
│              serves 6 JSON endpoints                     │
│                         │                               │
│                         ▼                               │
│              Next.js 16 (SSR)                            │
│              fetches API → renders HTML                  │
│                         │                               │
│                         ▼                               │
│              Nginx (:80)                                 │
│              reverse proxy → Next.js                     │
│              serves static assets                        │
│                         │                               │
└─────────────────────────┼───────────────────────────────┘
                          │
                          ▼
                   Internet User
                   http://100.107.117.23
```

## Event Object Lifecycle

```
Article (80 in DB)
  │
  ├─ build_fingerprint()
  │    subject · action · object · topic · country
  │
  ├─ fingerprint_score()
  │    pairwise comparison: anchor match → 100
  │    location mismatch → 0 (hard reject)
  │
  ├─ cluster()
  │    EVENT_THRESHOLD=50 → event
  │    MERGE_THRESHOLD=75 → strong merge
  │
  └─ Event Dossier (9 events)
       ├─ evidence  [quotes from articles]
       ├─ source_chain [who broke, who followed]
       ├─ timeline  [key moments by hour]
       ├─ facts     [SAO structured]
       └─ confidence [4-factor: authority + coherence + diversity + volume]
```

## Key Files

| File | Role | Location |
|------|------|----------|
| `news_intel.db` | Event Registry SQLite | `~/.hermes/.../news_intel/` |
| `aggregator.py` | Produces Event Dossiers | `search-engine-v2/scripts/news_intel/` |
|| `db.py` (backend) | FastAPI reads SQLite | `news-intel-web/backend/` |
|| `main.py` | 6 API endpoints | `news-intel-web/backend/` |
|| `page.tsx` (×6) | Next.js pages | `news-intel-web/frontend/src/app/` |

## fetch_stats — 抓取成功率统计表 (PostgreSQL)

每条 pipeline 运行后自动推送，记录域名/RSS源 × 抓取策略维度的成功/失败计数。

### 表结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | SERIAL PK | 自增主键 |
| `domain` | VARCHAR(200) | 域名（可为 NULL，与 source_name 互斥） |
| `source_name` | VARCHAR(200) | RSS 源名称（可为 NULL，与 domain 互斥） |
| `strategy` | VARCHAR(50) | 抓取策略：`rss_fulltext` / `direct` / `archive` / `scrapling` / `searxng_alt` / `tavily` |
| `ok_count` | INTEGER | 成功次数 |
| `fail_count` | INTEGER | 失败次数 |
| `run_at` | TIMESTAMP | 统计批次运行时间 |
| `created_at` | TIMESTAMP | 记录插入时间（DEFAULT NOW()） |

### 写入规则

每条记录 **domain 和 source_name 互斥**：统计域名的行 `domain` 有值、`source_name` 为 NULL；统计 RSS 源的行反之。

```json
// 域名统计
{"domain": "wsj.com",        "source_name": null,  "strategy": "direct",  "ok": 80, "fail": 20, "run_at": "..."}
// RSS 源统计
{"domain": null,             "source_name": "Reuters World", "strategy": "archive", "ok": 5, "fail": 2, "run_at": "..."}
```

### 查询示例

```sql
-- RSS 源成功率排行（用于调整源订阅）
SELECT source_name, strategy,
       SUM(ok_count) AS ok, SUM(fail_count) AS fail,
       ROUND(SUM(ok_count)*100.0 / NULLIF(SUM(ok_count+fail_count),0), 1) AS pct
FROM fetch_stats
WHERE source_name IS NOT NULL
GROUP BY source_name, strategy
ORDER BY SUM(ok_count+fail_count) DESC;

-- 域名成功率排行（用于调整抓取策略配置）
SELECT domain, strategy,
       SUM(ok_count) AS ok, SUM(fail_count) AS fail,
       ROUND(SUM(ok_count)*100.0 / NULLIF(SUM(ok_count+fail_count),0), 1) AS pct
FROM fetch_stats
WHERE domain IS NOT NULL
GROUP BY domain, strategy
ORDER BY SUM(ok_count+fail_count) DESC;

-- 近 7 天趋势
SELECT DATE(run_at) AS day, strategy,
       SUM(ok_count) AS ok, SUM(fail_count) AS fail
FROM fetch_stats
WHERE run_at >= NOW() - INTERVAL '7 days'
GROUP BY day, strategy ORDER BY day DESC;
```

### API 端点

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `POST` | `/internal/fetch_stats` | `X-Internal-Token` | Pipeline 写入统计 |
| `GET` | `/admin/fetch_stats` | JWT (admin) | 查询全部统计 |

### 抓取策略一览

| 策略 | cost | 说明 |
|------|------|------|
| `rss_fulltext` | 0 | 直接从 RSS description 提取正文（HTML 密度 <30%） |
| `direct` | 1 | httpx 直连 + trafilatura 抽取 |
| `archive` | 1 | web.archive.org 存档直连 |
| `scrapling` | 2 | Scrapling StealthyFetcher（绕过 Cloudflare 等反爬） |
| `searxng_alt` | 2 | SearXNG 搜索替代 URL（score 80-89，免费） |
| `tavily` | 5 | Tavily AI 搜索摘要（score ≥90，付费） |
