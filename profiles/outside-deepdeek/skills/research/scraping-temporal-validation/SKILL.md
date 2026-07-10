---
name: scraping-temporal-validation
description: 时间一致性校验 — V1五条硬规则检测 URL年份/发布时间/标题年份/Last Updated 冲突，防止抓到旧文章
tags:
  - temporal-validation
  - timestamp
  - url-validation
  - v1-rules
  - confidence-scoring
category: research
---

# 时间校验 (Temporal Validation) — V1 修复版

## 核心防错能力

防止抓到"看起来是最新、实际是去年/前年"的旧文章（典型场景：WSJ URL 中 2025/2026 混淆）。

## V1 五条硬规则

### 1️⃣ URL年份优先规则
```python
if URL.year != content.year:  # 如 URL: 06-30-2025, 内容: June 30, 2026
    flag = HIGH_RISK
```
→ 不得仅凭此 URL 执行爬取

### 2️⃣ Last Updated 硬约束
```python
Last Updated = TRUSTED SOURCE  # 搜索摘要中的字段
# 如: "Last Updated: June 30, 2025 at 9:44pm ET"
# 如果这个字段与 URL 年份不符，说明 URL 指向旧页面
```

### 3️⃣ 多源一致性检查
```python
signals = [
    extract_year_from_url(url),           # URL 路径年份
    extract_year_from_title(),            # 标题提及年份
    extract_year_from_content(),          # 正文年份
    extract_last_updated_year(),          # Last Updated 年份
]
if len(set(filter(None, signals))) > 1:
    MUST NOT proceed without re-query
```

### 4️⃣ Wayback 降级规则
Wayback Machine 是**存档证据源**，不是**时序真相源**。  
返回的快照可能包含跨年复用的内容，不代表这是你需要的最新版本。

### 5️⃣ 冲突触发机制（关键）
**ANY 不一致** 出现在以下三个信号之间：
- URL 中的年份
- 标题/描述中的日期
- Last Updated 字段

→ **强制重新查询 live source**，直到找到时间线完全一致的 URL。

## 陈旧预警
```python
if published_days_ago > 30 AND expects_breaking_news:
    confidence = "medium"  # 陈旧内容预警
```

## 执行流程
```python
1. 从 URL 路径提取年份（如 /06-30-2025/ → 2025）
2. 从抽取出的 published_at 提取年份
3. 从标题/正文提取年份
4. 从搜索摘要提取 Last Updated 年份
5. 三方对比：不一致 → confidence="low" → 重新搜索
```
