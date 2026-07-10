---
name: scraping-archive-fallback
description: Wayback Machine 归档降级策略 — 直连/JS渲染均失败时，从 web.archive.org 拉取历史快照兜底
tags:
  - wayback-machine
  - archive-org
  - web-archive
  - fallback
  - paywall-bypass
  - datadome
category: research
---

# 归档降级 (Archive Fallback)

## 适用场景
- 原页面 404 / 内容被撤下
- 反爬彻底拦截（DataDome / Cloudflare）
- 已知 URL 但需要获取历史版本

## 核心原理
WSJ/Reuters 等付费新闻站的文章发布后会被 web.archive.org 自动存档。  
通过存档抓取而非直连，可完全绕过 DataDome 等反爬系统。

## 操作步骤

### Step 1: 构造存档 URL
```python
# 格式: https://web.archive.org/web/{YYYYMMDDHHMMSS}/{original_url}
archive_url = f"https://web.archive.org/web/20260630000000/https://www.wsj.com/..."
```

### Step 2: 提取
```python
from hermes_tools import web_extract
result = web_extract(urls=[archive_url])
```

### Step 3: 如果今日未存档，尝试临近日期
Wayback Machine 收录有延迟。尝试不同时间段：
```python
urls_to_try = [
    "https://web.archive.org/web/20260630000000/https://www.wsj.com/...",
    "https://web.archive.org/web/20260629120000/https://www.wsj.com/...",
    "https://web.archive.org/web/20260629000000/https://www.wsj.com/...",
]
```

## V1 规则：Wayback 降级
Wayback Machine 是 **存档证据源（archival evidence）**，不是 **时序真相源（temporal truth source）**：
- Wayback 返回一个**曾存在过的页面快照**，不代表这是你需要的最新年份版本
- 例如 `06-30-2025` 的 Wayback 快照可能包含 2026 年的内容（因为该 URL 被 WSJ 跨年复用）
- 使用后必须执行 06_temporal_validation 校验快照时间
- 输出时附带标注 `数据来源: web.archive.org 历史快照`

## 已知成功案例
- ✅ WSJ live blog 子卡片详情（2024-2025内容已存档）
- ✅ WSJ 单篇付费文章（2025年及以前已存档）
- ❌ 今日/当日实时内容（尚未被收录）
