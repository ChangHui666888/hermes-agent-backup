---
name: scraping-entity-driven
description: 实体驱动抓取策略 — 以 person/company/event 为中心，扩展查询后批量搜索+排序+抽取，按时间线聚合。执行铁律：读完skill后同一轮必须发出第一个工具调用。
tags:
  - entity-driven
  - person-tracking
  - company-monitoring
  - timeline-aggregation
  - batch-scraping
  - execution-iron-rule
category: research
---

# 实体驱动抓取 (Entity-Driven)

## 适用场景

以"实体"为中心的舆情/事件追踪（如"马斯克"、"某公司财报"、"美联储"），而非以单个 query 或 URL 为起点。

## 执行铁律（重要）

读完本 skill 后，**同一轮响应中必须发出第一个工具调用**，不得：
- ❌ 停在"我打算做以下步骤..."的计划阶段
- ❌ 让用户"选择关注方向"后再继续
- ❌ 只描述流程而不实际调用 web_search / web_extract

写计划可以，但必须紧接着执行。plan→execute 断裂是严重违例。

## 执行流程

```
实体名称 (如 "马斯克")
    │
    ▼
Step 1: 实体扩展（必须在这一轮执行）
    │  web_search(query="Trump site:reuters.com")
    │  web_search(query="Donald Trump site:apnews.com")
    ▼
Step 2: 批量搜索（多来源独立查询，不用 OR）
    │  ✅ 正确：每个来源单独搜
    │     web_search(query="Trump site:reuters.com")
    │     web_search(query="Trump site:apnews.com")
    │  ❌ 错误：一次 OR 查询
    │     web_search(query="site:reuters.com Trump OR site:wsj.com Trump")
    ▼
Step 3: 候选排序
    │  scraping-multi-url-candidate 打分选出每个查询的最佳URL
    │  或 s02_rank.py 算法（可通过 terminal + Python 调用）
    ▼
Step 4: 批量抽取
    │  scraping-direct-extract 对每个最佳URL提取正文
    │  web_extract(urls=[best_url])
    ▼
Step 5: 时间校验
    │  scraping-temporal-validation 检查每个结果
    │  core/temporal.py (freshness_mode感知)
    ▼
Step 6: 按时间线聚合
    │  按 published_at 排序，形成事件时间线
```

## 实体扩展模板

```python
ENTITY_EXPAND_PROMPT = """
给定实体名称，生成用于新闻搜索的扩展查询列表
（包含常见别名、英文名、相关关键词，5个以内）
"""
```

## 陷阱

- **不要在读过 skill 后停在计划阶段** — 同一轮必须发出第一个工具调用
- **不要一次 OR 搜多个来源** — 每个来源单独搜索（很多搜索引擎不支持 OR 跨站）
- **不要问用户"选哪个方向"** — 全自动执行，所有方向都走
- **execute_code 当前不可用** — 用 Hermes 工具直接调用（web_search / web_extract）

## 适用场景示例

| 实体类型 | 示例 | 扩展查询 |
|---------|------|---------|
| 人物 | 川普 | Donald Trump, Trump tariffs, 川普 最新 |
| 公司 | OpenAI | OpenAI, Sam Altman, GPT, AGI |
| 事件 | 美联储加息 | Federal Reserve, Fed rate, FOMC, Powell |
