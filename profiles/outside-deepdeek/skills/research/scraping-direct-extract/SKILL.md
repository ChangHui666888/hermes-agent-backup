---
name: scraping-direct-extract
description: 直连抓取策略 — URL → HTML → 使用 web_extract 或 Scrapling 提取正文，配合 Wayback 降级
tags:
  - scraping
  - direct-extract
  - web-extract
  - scrapling
  - paywall
category: research
---

# 直连抓取 (Direct Extract)

## 适用场景
已知确切 URL 的单页面新闻文章（WSJ / Reuters / Bloomberg 等）。

## 优先级策略

### 等级1: web_extract 直连（最快）
```python
from hermes_tools import web_extract
result = web_extract(urls=["https://www.wsj.com/..."])
# 如果成功 → 返回 Markdown 格式的正文
```

### 等级2: Scrapling StealthyFetcher
```python
from scrapling import StealthyFetcher
sf = StealthyFetcher()
resp = sf.fetch("https://www.wsj.com/...", timeout=30000)
html = resp.html
# 用 CSS 选择器提取标题和正文
```

### 等级3: Wayback Machine 归档（DataDome 保护时）
```python
archive_url = f"https://web.archive.org/web/20260630000000/{original_url}"
result = web_extract(urls=[archive_url])
```

## 失败信号
- HTML 长度 < 200 字符 → 反爬拦截
- HTTP 401/403 → DataDome/Cloudflare 保护
- 页面包含 'captcha' / 'Please enable JS' → 需要等级2或3

## 成功后的下一步
```python
# 提取字段后，必需执行时间校验
from hermes_tools import web_search
# 检查搜索摘要中的 Last Updated 与 URL 年份是否一致
```

## 参考
- `wsj-paywall-archive-scrape` — WSJ 专用策略（含 DataDome 绕过）
- `anti-bot-scraping` — 通用反爬绕过框架（含站点级配置方法）
- `web-scraping-pipeline` — 10策略调度系统（含降级链路）
