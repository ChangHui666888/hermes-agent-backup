# 全场景实测记录 — 2026-07-01

> 验证 search-engine-v2 级联引擎在真实 Hermes 环境中的行为。
> 测试方法：直接调用 Hermes 工具（web_search / web_extract）+
>            terminal + Python 调用 core/temporal.py 等纯逻辑模块。

## 测试覆盖

| 场景 | URL | cascade 路径 | cost | 结果 |
|:----:|-----|------------|:----:|:----:|
| WSJ 文章 → archive | wsj.com/business/deals/... | direct❌→archive✅ | 1 | 全文获取成功 |
| WSJ Live Blog 直连 | wsj.com/livecoverage/06-30-2026 | direct✅ | 1 | 完整Markdown |
| query→Reuters | reuters.com/business/fed-2026 | search→rank→direct✅ | 1 | Fed点阵图分析 |
| Reuters 直连 | reuters.com/nearly-half-fed... | direct✅ | 1 | 全文+结构化 |
| 实体追踪 Trump | 多源 | search×5→extract | 1 | 4个关键事件 |
| Newsweek 直连 | newsweek.com/july-4-mishaps | direct✅ | 1 | 全文+4个事故 |
| CNBC（模拟） | — | direct→scrapling | 1 | Mock通过 |

## 验证的纯逻辑模块

| 模块 | 测试内容 | 结果 |
|------|---------|:----:|
| `core/temporal.py` | 年份冲突检测、freshness_mode感知、陈旧预警 | ✅ |
| `skills/s02_rank.py` | 域名权威度+年份+相关度打分 | ✅ |
| `config/domain_profiles.py` | 16个域名画像查表 | ✅ |
| `skills/s04_wsj.py` | 时间戳正则（修复后支持 MM-DD-YYYY） | ✅ 修复后 |

## 发现的 Bug

1. **WSJ 时间戳正则不完整**：`s04_wsj.py` 的 `WSJ_DATE_RE` 只匹配 `/YYYY/MM/DD/`，遗漏 live blog 的 `06-30-2025` 格式
   → 修复：新增 `WSJ_DATE_ALT_RE` + `_extract_url_year()` 函数
   
2. **scripts 目录结构扁平化**：`web-scraping-pipeline` 初始集成时所有文件被放到 `scripts/` 根目录，`from skills import` 报错
   → 修复：重建 `scripts/skills/` 子包 + `__init__.py`

## 已确认的域名行为

| 域名 | direct | archive | 验证日期 |
|------|:------:|:-------:|----------|
| wsj.com 文章页 | ❌ DataDome | ✅ 稳定 | 2026-07-01 |
| wsj.com live blog主页 | ✅ 偶尔 | N/A | 2026-07-01 |
| reuters.com | ✅ 100% | N/A | 2026-07-01 |
| newsweek.com | ✅ 100% | N/A | 2026-07-01 |
