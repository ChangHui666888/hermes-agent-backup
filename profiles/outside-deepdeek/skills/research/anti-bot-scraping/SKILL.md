---
name: anti-bot-scraping
description: 爬取受反爬保护（DataDome/Cloudflare/CAPTCHA/付费墙）的新闻网站。策略优先级：web_extract直连 → Wayback Machine存档 → Scrapling StealthyFetcher → 搜索摘要补充。支持 WSJ/NYT/Bloomberg 等主流付费站
tags:
  - scraping
  - 爬取
  - paywall
  - 付费墙
  - antibot
  - datadome
  - cloudflare
  - captcha
  - wayback-machine
  - web-archive
  - scrapling
  - stealthy-fetcher
  - wsj
  - 华尔街日报
  - wall-street-journal
  - bloomberg
  - news-scraping
  - content-extraction
category: research
---

# Anti-Bot Scraping: Bypassing Paywalls & CAPTCHAs on News Sites

## 适用场景

需要提取受反爬保护的主流新闻/财经网站（WSJ、Bloomberg、NYT、FT等）的内容时。这些网站部署 DataDome、Cloudflare Turnstile 等主动式反爬系统，常规 requests 和 headless browser 均可被阻断。

## 策略优先级（从上到下尝试）

### 第1层: web_extract 直连 ⭐ 首选

Hermes 内建的 `web_extract` 工具在某些情况下能绕过反爬系统，**始终优先尝试**。

```
web_extract(urls=["https://www.wsj.com/livecoverage/..."])
```

- ✅ **成功案例**: WSJ 主 live blog 页面可直接通过 web_extract 提取全文
- ⚠️ WSJ 子卡片（card/URL）通常被阻断
- ⚠️ NYT 通常被阻断
- 返回全文 Markdown，无 CAPTCHA

### 第2层: Wayback Machine 存档

当直连被阻断时，检查 web.archive.org 是否有存档：

```
https://web.archive.org/web/20260630000000/https://原始URL
```

通过 `web_extract` 访问存档：
```
web_extract(urls=["https://web.archive.org/web/20260630000000/https://www.wsj.com/..."])
```

- ✅ **成功案例**: WSJ 文章和 live blog 卡片存档可通过此方式获取
- ❌ 当天最新文章可能尚未收录（存档延迟数小时至一天）
- 路径中的时间戳可以调整（`20260629` = 前一天的）

### 第3层: Scrapling StealthyFetcher

当以上都失败时，尝试本地 Scrapling 库。

```python
from scrapling import StealthyFetcher
sf = StealthyFetcher()
resp = sf.fetch(url, timeout=30000)  # 注意: 用 .fetch() 不是 .get()
html = resp.html
```

- 使用 patchright (Playwright) + Chrome + 指纹伪装
- ✅ 可应对 Cloudflare Turnstile 级别反爬
- ❌ WSJ DataDome 仍返回 401（阻断失败）
- ❌ 对环境有一定要求：需安装 curl_cffi / browserforge / patchright+Chromium / msgspec

**安装状态确认**（已安装于 Hermes venv）:
```bash
uv pip list | grep -iE "scrapling|curl_cffi|browserforge|patchright|msgspec"
```

如需安装Chromium浏览器：
```bash
python -m patchright install chromium
```

### 第4层: 搜索摘要补充

当以上均无法获取全文时，通过 web_search 获取搜索结果摘要作为替代信息源。

```python
web_search(query="site:wsj.com "关键词" + 日期")
```

- 搜索摘要通常包含文章首段或核心描述
- 可用于拼凑文章大意

## ⚠️ V1 时间校验 — 每次抓取前必须执行

在抓取任何 WSJ/Bloomberg/NYT 等新闻站之前，先执行时间一致性校验。

**WSJ 特有陷阱 — URL 跨年复用：**
WSJ 的 live blog URL 路径中包含年份段（如 `06-30-2025`），但该 URL 可能被 WSJ 跨年复用，内容显示 "June 30, 2026"。搜索摘要中会包含 `Last Updated: June. 30, 2025 at 9:44pm ET`。

**校验三步走：**
```python
1. 对比 URL 中的年份 vs 搜索摘要中的 Last Updated 年份
2. 对比 URL 中的年份 vs 标题/内容中的年份
3. 若不一致 → 标记 confidence="low" → 重新搜索年份匹配的 URL
```

**详细规则见** `skill:web-scraping-pipeline` → 06 时间校验 V1 五条硬规则。

## 添加新站点参考

当针对某个特定站点成功提取内容后，在 `references/` 目录下添加站点文档：
```
skill_write_file(name='anti-bot-scraping', file_path='references/站点名.md', content='...')
```

参考文件应包含：
- 站点名称和域名
- 反爬级别（DataDome / Cloudflare / 简单付费墙）
- 成功的抓取策略组合
- 已知可用的 URL 模式和示例
- 已知被阻断的模式
- 已验证的工作案例（时间范围和提取了什么内容）
