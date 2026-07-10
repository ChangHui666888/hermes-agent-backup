---
name: web-scraping-pipeline
description: 网页抓取 Pipeline — 10策略调度系统 + V1 时间校验 + 降级链路，适用 WSJ/Reuters/Bloomberg 等付费新闻站。脚本目录结构已修复（skills/子包）。
tags:
  - scraping
  - web-scraping
  - pipeline
  - news-extraction
  - wsj
  - reuters
  - bloomberg
  - temporal-validation
  - wayback-machine
  - live-blog
  - multi-source-merge
  - entity-driven
  - paywall-bypass
category: research
---

# Web Scraping Pipeline — 十策略调度系统

## 系统架构

```
用户输入 (URL / query / entity)
        │
        ▼
  ┌─────────────┐
  │   Router    │   ← 意图识别 + 降级链路 + 强制时间校验
  └──────┬──────┘
         │
  ┌──────┴──────┐
  │  策略选择   │
  └──────┬──────┘
         │
  ┌──────┴──────────────────────────────────────────┐
  │  主链路: 04_structured → 07_js_render → 08_archive  │
  │  直播页: 05_live_blog_cards                      │
  │  实体驱动: 10_entity_driven                      │
  └──────┬──────────────────────────────────────────┘
         │
  ┌──────┴──────┐
  │  06_temporal │   ← 强制时间校验（URL年份/发布时间/标题）
  └──────┬──────┘
         │
  ┌──────┴──────┐
  │  09_merge   │   ← 多源融合（可选）
  └─────────────┘
```

## 十策略清单

| # | 策略 | 功能 | 工具依赖 |
|---|------|------|---------|
| 01 | **直连抓取** | URL → HTML → 提取正文 | web_extract / Scrapling |
| 02 | **搜索→选择→抓取** | query → 搜索 → 选URL → 提取 | web_search + web_extract |
| 03 | **多候选排序** | 多个候选URL打分排序选出最佳 | web_search + 域名权重算法 |
| 04 | **结构化新闻** | HTML → 固定Schema(标题/时间/正文/相关代号) | web_extract + LLM |
| 05 | **直播卡片** | 直播页 → 时间序事件卡片数组 | web_extract + 卡片提取 |
| 06 | **时间校验** ⭐ | URL年份/发布时间/标题三方一致性校验 | 纯算法（无外部依赖） |
| 07 | **JS渲染** | 动态页面 → headless渲染 → 提取 | Scrapling StealthyFetcher / Playwright |
| 08 | **归档降级** | 原页面失败 → Wayback Machine 兜底 | web_extract(archive.org) |
| 09 | **多源融合** | 多家媒体交叉验证 → 共识/分歧简报 | web_search + web_extract |
| 10 | **实体驱动** | person/company → 扩展查询 → 批量抓取 → 时间线聚合 | 2+3+4 组合 |

## 目录结构（已修复）

```
scripts/
├── __init__.py
├── demo.py              # Mock 测试入口
├── router.py            # 调度核心 ScrapingRouter
└── skills/              # ← 重建的子包（原文件被扁平化，已修复）
    ├── __init__.py      # 类导出清单
    ├── base.py          # BaseSkill / SkillResult
    ├── s01_direct_extract.py
    ├── s02_search_pick_extract.py
    ├── s03_multi_url_candidate.py
    ├── s04_structured_news.py
    ├── s05_live_blog_cards.py
    ├── s06_temporal_validation.py
    ├── s07_js_render.py
    ├── s08_archive_fallback.py
    ├── s09_multi_source_merge.py
    └── s10_entity_driven.py
```

**修复记录：** 初始集成时所有 .py 文件被扁平化存入 `scripts/`，导致 `from skills import ...` 报错 ModuleNotFoundError。修复：创建 `scripts/skills/` 子目录，将 s01~s10 + base.py 移入，创建 `__init__.py` 导出所有类。

## 执行铁律

`execute_code` 在 Hermes v0.17.0 中不可用（中间件参数不匹配）。替代方案：
- 调用 `terminal` + Python 执行纯算法模块（s06_temporal_validation.py 等）
- 直接调用 Hermes 工具（web_search / web_extract）
- **不得停在计划阶段** — 读过 skill 后同一轮必须发出第一个工具调用

## 06 时间校验 V2（增强版）

```python
signals = {
    "url_year": extract_year_from_url(url),
    "published_year": extract_year_from_article(),
    "title_year": extract_year_from_title(),
    "last_updated": extract_last_updated(),
    "content_year": extract_year_from_body(),
}

for signal_pair in combinations(signals, 2):
    if both_exist(signal_pair) AND not match(signal_pair):
        confidence = "low"
        trigger_re_query()
        break

if published_days_ago > 30 AND expects_breaking_news:
    confidence = "medium"
```

## 自动化降级链路

```
[04] Structured News  →  ❌ 失败
    ↓
[07] JS Render        →  ❌ 反爬拦截
    ↓
[08] Archive Fallback →  ✅ Wayback Machine 有存档 → 成功
    ↓
[06] Temporal Validation → 通过 → 输出 + "数据来源:历史快照" 标注
```

## 参考文件

- `scripts/skills/base.py` — 基础抽象类 (BaseSkill / SkillResult)
- `scripts/skills/s01_direct_extract.py` — 直连抓取
- `scripts/skills/s06_temporal_validation.py` — 时间校验
- `scripts/skills/s08_archive_fallback.py` — 归档降级
