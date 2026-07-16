# 完整流程与策略文档

## 一、Pipeline 全流程

```
┌─────────────────────────────────────────────────────┐
│ Step 0  清理占位行                                    │
│         删除 fetch_strategy=NULL 且 retry_count≥3    │
│         的空占位行，释放 URL 重新进入抓取队列            │
├─────────────────────────────────────────────────────┤
│ Step 1  Sync + Score                                │
│         RSS → news_intelligence (游标续拉, LIMIT 100) │
│         五维评分: source/impact/entity/market/velocity │
│         Tier A >90 / Tier B 60-90 / Tier C <60       │
├─────────────────────────────────────────────────────┤
│ Step 2  RSS FullText                                │
│         RSS description → news_content               │
│         跳过 HTTP 抓取: HTML密度<30% + 长度≥200字      │
│         cost=0, strategy=rss_fulltext                │
├─────────────────────────────────────────────────────┤
│ Step 3  Fetch (batch.py)                            │
│         串行抓取 (max-workers=1, rate-delay=1.0s)    │
│         查询 domain_profiles → 策略级联 → 正文入库    │
│         retry_count 追踪, ≥3 → exhausted             │
├─────────────────────────────────────────────────────┤
│ Step 3.5 Recovery                                   │
│         SearXNG: score 80-89, 免费替代URL搜索, ≤10篇 │
│         Tavily:  score ≥90, AI摘要, ≤5篇              │
│         扫描全部空行，不依赖当前批次                    │
├─────────────────────────────────────────────────────┤
│ Step 4  Aggregate                                   │
│         规则引擎 SAO 抽取 → 事件聚类                  │
│         fingerprint → cluster → 21-field Event       │
├─────────────────────────────────────────────────────┤
│ Step 5  Cloud Sync                                  │
│         event_registry → PG events 表                │
│         HTTP POST /internal/events/batch              │
├─────────────────────────────────────────────────────┤
│ Step 6  Content Push                                │
│         news_content → PG articles 表                │
│         HTTP POST /internal/news/batch                │
└─────────────────────────────────────────────────────┘
```

## 二、增强流程 (LLM Enhancement)

```
Tier C (<60)  → enhance_python()  规则抽取, 零成本
Tier B (60-90)→ enhance_qwen()    Qwen3-1.7B 本地, 并发3
Tier A (>90)  → enhance_deepseek() DeepSeek V4, 云端API

LLM 并发: ThreadPoolExecutor(max_workers=3)
        可配置: LLM_CONCURRENCY 环境变量
DB 写入:  所有 LLM 调用完成后串行写入, 防锁死
```

## 三、抓取策略级联

### 3.1 策略列表

| # | 策略 | cost | 实现 | 说明 |
|---|------|------|------|------|
| 1 | `direct` | 1 | httpx.GET + trafilatura | Cookie持久化(DirectClientPool), 重试3次(408/429/5xx) |
| 2 | `google_cache` | 1 | httpx.GET webcache.googleusercontent.com | Google 缓存的快照 |
| 3 | `archive` | 1 | httpx.GET web.archive.org | Wayback Machine 存档 |
| 4 | `scrapling` | 2 | Scrapling StealthyFetcher | TLS指纹随机化, 共享单例(ScraplingPool), 绕过Cloudflare |
| 5 | `browser` | 3 | Playwright headless Chromium | JS渲染, domcontentloaded等待, article选择器fallback |
| 6 | `search_snippet` | 1 | 搜索API兜底 | 依赖外部search_func注入, 取搜索结果摘要 |
| 7 | `computer_use` | 5 | ❌ 批量禁用 | 仅手动触发, 桌面驱动不适合批处理 |

### 3.2 级联规则

```
查询 domain_profiles.get_profile(url)
  → 获取该域名的 strategy_order (按优先级排列)
  → 排除 known_failing 集合中的策略
  → skip_expensive=True 时额外排除 browser, computer_use
  → 逐策略尝试, 命中即停 (content_len ≥ min_content_len)
  → 全部失败 → SearXNG/Tavily recovery
```

### 3.3 域名画像 (domain_profiles.py)

**强反爬/付费墙 (DataDome):**
| 域名 | anti_bot | strategy_order | known_failing |
|------|----------|----------------|---------------|
| wsj.com | datadome | direct, google_cache, archive, search_snippet | scrapling, browser |
| bloomberg.com | datadome | direct, google_cache, archive, search_snippet | scrapling, browser |
| ft.com | datadome | direct, google_cache, archive, search_snippet | scrapling, browser |

**中等反爬 (Cloudflare):**
| 域名 | anti_bot | strategy_order | known_failing |
|------|----------|----------------|---------------|
| cnbc.com | cloudflare | direct, scrapling, archive, search_snippet | - |
| businessinsider.com | cloudflare | direct, scrapling, archive, search_snippet | - |
| investing.com | cloudflare | direct, google_cache, archive, search_snippet | scrapling, browser |
| investors.com | cloudflare | direct, google_cache, archive, search_snippet | scrapling, browser |

**无反爬/友好:**
reuters.com, apnews.com, newsweek.com, aljazeera.com, theguardian.com, bbc.com/bbc.co.uk, cnn.com, arxiv.org → `["direct"]`

**通用默认 (未命中域名画像):**
`["direct", "archive", "scrapling", "browser", "computer_use", "search_snippet"]`

## 四、关键参数

| 参数 | 值 | 位置 |
|------|-----|------|
| 单批文章数 | 100 | news-pipeline.py --limit |
| 游标续拉窗口 | 1小时 | news-pipeline.py --hours |
| 抓取并发 | 1 (串行) | pipeline.py --max-workers |
| 请求间隔 | 1.0s | pipeline.py --rate-delay |
| LLM 并发 | 3 | pipeline.py LLM_CONCURRENCY |
| LLM max_tokens | 500 | enhancers.py enhance_qwen |
| 管道总超时 | 1200s | pipeline_check.py |
| batch 超时 | 300s | pipeline.py |
| 重试次数 | 3 | fetchers.py MAX_RETRIES |
| 重试上限 | 3 → exhausted | auto-pipeline.py |
| SearXNG 上限 | 10篇/次 | auto-pipeline.py |
| Tavily 上限 | 5篇/次 | auto-pipeline.py |
| RSS FullText 门槛 | 200字, HTML密度<30% | auto-pipeline.py |

## 五、运行命令

```bash
# 完整管线 (RSS→Sync→Fetch→LLM→Aggregate→Cloud)
python pipeline_check.py run

# 单阶段
python pipeline_check.py check    # 健康检查
python pipeline_check.py rss      # RSS 扫描
python pipeline_check.py pipeline # 同步+评分+抓取+增强
python pipeline_check.py sync     # 云端同步

# 直接调用
python news-pipeline.py                    # 默认 100 篇
python news-pipeline.py --limit 50         # 小批量
python news-pipeline.py --hours 4          # 长时间窗口
python news-pipeline.py --catchup          # 追平积压
python news-pipeline.py --no-fetch         # 仅评分, 不抓取

# 自动管线 (cron)
python auto-pipeline.py

# E2E 测试
python test_e2e.py -v
python test_e2e.py --test T2
```

## 六、数据库表

| 表 | 位置 | 用途 |
|----|------|------|
| rss_raw | rss-archive.db | RSS 原始数据 |
| news_intelligence | news_intel.db | 评分后的文章 (tier/score/entities) |
| news_content | news_intel.db | 正文内容 (content_md/fetch_strategy/retry_count) |
| event_registry | news_intel.db | 聚合事件 |
| fetch_stats | PostgreSQL (云端) | 域名/RSS源抓取统计 |
| events | PostgreSQL (云端) | 同步后的事件 |
| articles | PostgreSQL (云端) | 同步后的文章 |

## 七、fetch_stats 表结构 (PG)

```
id            SERIAL PRIMARY KEY
domain        VARCHAR(200)         -- 域名 (与 source_name 互斥)
source_name   VARCHAR(200)         -- RSS 源名 (与 domain 互斥)
strategy      VARCHAR(50)          -- rss_fulltext/direct/archive/scrapling/searxng_alt/tavily
ok_count      INTEGER
fail_count    INTEGER
run_at        TIMESTAMP
created_at    TIMESTAMP DEFAULT NOW()
```

## 八、retry 机制

```
news_content.retry_count:
  0         → 首次尝试
  +1/次     → 每次 fetch 失败递增
  ≥3        → fetch_strategy = 'exhausted', 不再重试
  成功       → retry_count 重置为 0, fetch_strategy 更新为实际策略名

Step 0 清理: 删除 fetch_strategy=NULL AND content_md='' AND retry_count≥3
```
