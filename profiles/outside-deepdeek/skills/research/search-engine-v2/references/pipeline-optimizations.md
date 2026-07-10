# Pipeline 优化记录 (2026-07-10)

## 批量推送优化

### 问题
串行推送 19 篇文章：`for each: POST /internal/news` → 19 × 1.4s = 27s。Pipeline 本身 0.1s，推送占 99.6%。

### 解决
`POST /internal/news/batch` — 一次请求发送全部文章。

```python
# pusher.py
def push_batch(articles: list[dict]) -> dict:
    body = [build_article(a) for a in articles]
    resp = httpx.post(f"{base}/internal/news/batch", json=body)
    return resp.json()  # {"ok": 19, "fail": 0}
```

**效果**: 27s → 2s (-93%)

## Report 统计口径

### 问题
旧格式混淆 batch 和 cumulative:
```json
{"processed": 3, "tier_b": 19, "duplicate": 186}
```
processed=3（本轮新增）但 tier_b=19（累计），duplicate=186（累计）。

### 解决
```json
{
  "batch_input": 22,    "batch_new": 3,     "batch_duplicate": 19,
  "batch_tier_a": 0,    "batch_tier_b": 0,  "batch_tier_c": 3,
  "batch_enhanced": 0,  "batch_pushed": 3,  "batch_push_failed": 0,
  "total_a": 0,         "total_b": 19,       "total_c": 179,
  "total_articles": 95,
  "duration_pipeline_sec": 0.1, "duration_push_sec": 2.0, "duration_sec": 2.1
}
```

## 去重机制

```python
# sync.py — 跳过已评分
existing_urls = set(r[0] for r in dst.execute("SELECT article_url FROM rss_raw").fetchall())
rows = [r for r in rows if r["link"] not in existing_urls]

# pipeline.py — 跳过已增强
LEFT JOIN news_content nc ON nc.intel_id = ni.id
WHERE ni.tier IN ('A', 'B') AND nc.id IS NULL
```

## 性能计时

```python
duration_sec         # 总耗时
duration_pipeline_sec # 纯业务（elapsed - push_duration）
duration_push_sec    # 推送耗时
```

## Qwen 参数调整

| 参数 | 旧值 | 新值 |
|------|:--:|:--:|
| 超时 | 30s | 60s |
| max_tokens | 150 | 1024 |
| 调用次数/篇 | 3 | 1（合并 prompt） |

`QMERGE_PROMPT` 一次调用返回 `{tags, companies, persons, summary_cn}`。
