---
name: scraping-live-blog-cards
description: 直播流卡片抽取策略 — 解析 WSJ/Reuters live coverage 页面，将时间序更新拆解为独立事件卡片
tags:
  - live-blog
  - live-coverage
  - wsj
  - reuters
  - card-extraction
  - event-stream
category: research
---

# 直播流卡片抽取 (Live Blog Cards)

## 适用场景
WSJ/Reuters 的 "live coverage" 页面（实时行情直播）。
内容是按时间倒序排列的更新卡片（每条带时间戳+小标题+正文）。

## 页面结构
```
URL 模式: https://www.wsj.com/livecoverage/stock-market-today-{topic}-{date}

页面组成:
├── 主文章（Lead Article）— 今日概述
├── 更新卡片 1 — 10:30am ET | 某事件
├── 更新卡片 2 — 10:15am ET | 另一事件
├── ...
```

每张卡片是一个独立子页面：
```
https://www.wsj.com/livecoverage/.../card/卡片标题-ID
```

## 提取步骤

### Step 1: 获取主页面
```python
from hermes_tools import web_extract
page = web_extract(urls=["https://www.wsj.com/livecoverage/..."])
# 返回: 主文章正文 + 卡片摘要列表
```

### Step 2: 补充卡片详情
子卡片通常被 DataDome 阻断。使用搜索摘要补充：
```python
from hermes_tools import web_search
# 搜索特定卡片标题获取更多详情
details = web_search(query=f'WSJ "{card_title}" June 30 2026')
```

### Step 3: 如果直连失败，尝试 Wayback
```python
archive_url = f"https://web.archive.org/web/.../{card_url}"
card = web_extract(urls=[archive_url])
```

## V1 适配
直播页 URL 包含日期段（如 06-30-2026），提取前必须执行时间校验：
- 检查 URL 中的年月日是否与 "Last Updated" 一致
- 区分 `2025` 和 `2026` 两个不同的页面前缀
