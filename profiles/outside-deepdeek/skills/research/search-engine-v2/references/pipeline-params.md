# Pipeline 生产参数速查 (2026-07-11 锁定)

## 评分阈值

```python
# scorer.py:244
if total >= 90: tier = "A"  # DeepSeek V4 Flash
elif total >= 60: tier = "B"  # Qwen3-1.7B
else: tier = "C"  # Python rules
```

## Qwen3 配置

```
timeout: 60s | max_tokens: 1024 | 调用: 1次/篇（合并标签+实体+摘要）
不可用时: 全局降级 → Python规则
```

## DeepSeek 配置

```
模型: deepseek-v4-flash | timeout: 45s
无Key时: 降级Python规则
```

## 推送配置

```
端点: POST /internal/news/batch | timeout: 5s | 模式: 批量
```

## RSS 配置

```
隔离: 3次失败 → 30min隔离 | 频率: 5min | 源: 94
```

## Cron 命令

```powershell
hermes cron add "every 5m"  --name rss-scan --script rss-scanner.py --workdir "C:\Users\ChangHui\AppData\Local\hermes\scripts" --no-agent
hermes cron add "every 30m" --name news-pipeline --script news-pipeline.py --workdir "C:\Users\ChangHui\AppData\Local\hermes\scripts" --no-agent
```

## 去重

```
评分去重: sync.py:47-48 (rss_raw existing_urls)
增强去重: pipeline.py:66 (LEFT JOIN news_content WHERE nc.id IS NULL)
```

## V1 Schema (PostgreSQL)

```
11 tables: sources, articles, entities, categories, tags, events, insights, assets
6 associations: article_entity, event_article, event_entity, article_category, article_tag, event_asset
```
