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

| # | 策略 | cost | 实现 | 说明 |
|---|------|------|------|------|
| 1 | `direct` | 1 | httpx.GET + trafilatura | Cookie持久化(DirectClientPool), 重试3次(408/429/5xx) |
| 2 | `google_cache` | 1 | httpx.GET webcache.googleusercontent.com | Google 缓存的快照 |
| 3 | `archive` | 1 | httpx.GET web.archive.org | Wayback Machine 存档 |
| 4 | `scrapling` | 2 | Scrapling StealthyFetcher | TLS指纹随机化, 共享单例(ScraplingPool), 绕过Cloudflare |
| 5 | `browser` | 3 | Playwright headless Chromium | JS渲染, domcontentloaded等待, article选择器fallback |
| 6 | `search_snippet` | 1 | 搜索API兜底 | 依赖外部search_func注入, 取搜索结果摘要 |
| 7 | `computer_use` | 5 | ❌ 批量禁用 | 仅手动触发, 桌面驱动不适合批处理 |

### 域名画像速查

**强反爬/付费墙 (DataDome):** wsj.com, bloomberg.com, ft.com — direct+google_cache+archive+search_snippet, scrapling/browser known_failing

**中等反爬 (Cloudflare):** cnbc.com, businessinsider.com, investing.com, investors.com

**无反爬/友好:** reuters.com, apnews.com, newsweek.com, aljazeera.com, theguardian.com, bbc.com/bbc.co.uk, cnn.com, arxiv.org — direct only

## 四、关键参数

| 参数 | 值 | 位置 |
|------|-----|------|
| 单批文章数 | 100 | news-pipeline.py --limit |
| 抓取并发 | 1 (串行) | pipeline.py --max-workers |
| 请求间隔 | 1.0s | pipeline.py --rate-delay |
| LLM 并发 | 3 | pipeline.py LLM_CONCURRENCY |
| LLM max_tokens | 500 | enhancers.py enhance_qwen |
| 管道总超时 | 1200s | pipeline_check.py |
| 重试上限 | 3 → exhausted | auto-pipeline.py |

## 五、运行命令

```bash
python pipeline_check.py check    # 健康检查
python pipeline_check.py run      # 完整管线
python news-pipeline.py --limit 50   # 小批量
python auto-pipeline.py           # 自动管线 (cron)
python test_e2e.py -v             # E2E 测试
```
