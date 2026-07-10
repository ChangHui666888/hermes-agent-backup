---
name: scraping-multi-url-candidate
description: 多候选URL排序策略 — 搜索结果中按域名权威度+年份+相关度打分，选出最佳URL
tags:
  - url-ranking
  - candidate-selection
  - domain-authority
  - search-result
category: research
---

# 多候选URL排序 (Multi-URL Candidate)

## 适用场景
搜索结果中混杂了旧文章、聚合页、无关站点，需要打分排序选出最佳候选。

## 打分维度

| 维度 | 权重 | 说明 |
|------|:----:|------|
| 域名权威度 | +3 | wsj/reuters/bloomberg 最高分 |
| 聚合页特征 | -3 | 含 /tag/ /topic/ /search/ 降权 |
| 标题相关度 | +0.5/词 | 标题与查询词的重叠数 |
| 年份匹配 | +1/-1 | 今年内容加分，往年内容减分 |

## 执行流程
```python
from hermes_tools import web_search

# Step 1: 搜索
results = web_search(query="site:wsj.com 美联储利率 2026")

# Step 2: 打分排序
candidates = results["data"]["web"]
ranked = sorted(candidates, key=lambda c: score(c, query), reverse=True)

# Step 3: 取最佳
best = ranked[0]

# Step 4: 验证（调用时间校验）
# 检查 best 的 URL 年份 vs 标题年份 vs Last Updated
```
