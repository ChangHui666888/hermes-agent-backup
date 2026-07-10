# News Intelligence Pipeline（云部署后新增）

## 多级数据持久化

整个系统现在有 **3 个数据库**：

### 1. rss-archive.db（本地 SQLite）
RSS 扫描器输出。94 源，每 5 分钟更新。
```sql
rss_articles(id, source, title, summary, link, category, date, created_at)
```

### 2. news_intel.db（本地 SQLite）
评分 + 增强结果。三表：
```sql
rss_raw           — RSS 原始数据（guid, source, article_url, title, description, ...）
news_intelligence — 评分（score_total, tier, category, tags, entities, velocity_count）
news_content      — 抓取正文 + 分析（content_md, summary_cn, extraction_method, llm_model）
```

### 3. PostgreSQL（云端）
FastAPI 后端存储。六表：
```sql
articles          — 新闻正文 + 分析（url UNIQUE, title, content_md, tags, entities, analysis, tier）
users             — 用户（email, password_hash, level）
subscriptions     — 标签订阅（user_id, tag）
ads               — 广告（image_url, link_url, position）
settings          — 系统配置（key, value）
logs              — 操作日志
```

## Hermes → 云端数据流

```
news_intel/pipeline.py
    │
    ├─ L0: RSS 同步 (sync.py: rss-archive.db → news_intel.db)
    ├─ L1: 五维评分 (scorer.py)
    ├─ L2: Intelligence Router (router.py: Tier A/B/C 分流)
    ├─ L3: 全文抓取 (batch.py, 仅 Tier A/B)
    ├─ L4: 脚本抽取 (extractor.py)
    ├─ L5: 时间校验 (temporal.py)
    ├─ L6: 三层增强 (enhancers.py)
    └─ L7: 本地入库 (news_intel.db)
         │
         │ pusher.py: POST /internal/news
         ▼
    云端 FastAPI → PostgreSQL
```

## 推送器配置

```python
# news_intel/pusher.py
API_BASE = "http://100.107.117.23:8001"  # 或环境变量 NEWS_API_BASE
INTERNAL_TOKEN = "hermes-pipeline-secret-2026"  # 需与云端一致
```

## 云端 FastAPI 内部认证

```python
# routes/internal.py
INTERNAL_TOKEN = "hermes-pipeline-secret-2026"

@router.post("/news")
def push_news(article: ArticleIn, x_internal_token: str = Header(...)):
    if x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(403)
    # INSERT ON CONFLICT (url) DO UPDATE
```
