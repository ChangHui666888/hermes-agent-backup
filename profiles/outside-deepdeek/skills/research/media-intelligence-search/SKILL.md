---
name: media-intelligence-search
description: 三级搜索架构 + RSS 持续监控系统 — SearXNG 广覆盖发现信源 + 事件分级 + Tavily 深度分析 A 级事件 + 98源RSS扫描 cron 每5分钟
version: 3.2
author: Hermes Agent
tags: [search, intelligence, media-monitoring, source-discovery, cross-validation, rss, cron, news-scanner]
---

# Media Intelligence Search (V3.1)

## 核心理念

```
SearXNG ≠ 新闻搜索引擎
SearXNG = 来源发现引擎（Source Discovery Engine）
```

不要用 SearXNG 搜宽泛关键词。要用 SearXNG **搜指定来源内的特定实体**。

RSS + SearXNG 互补：RSS 负责持续跟踪已知源（推送），SearXNG 负责发现未知信源（拉取）。

---

## 一、三级搜索架构

```
                Query Planner
                      │
        ┌─────────────┴─────────────┐
        │                           │
        ▼                           ▼
   SearXNG                     Tavily
 Source Discovery          Semantic Discovery
        │                           │
        ▼                           ▼
 第一手来源                     AI摘要（仅A级事件）
        │                           │
        └─────────────┬─────────────┘
                      ▼
               Cross Validator
                      │
                      ▼
               Evidence Builder
```

- **SearXNG**：负责「发现」→ 广覆盖，找到第一手来源
- **Tavily**：负责「理解」→ 仅用于 A 级事件的深度分析
- 二者**不重复搜索**，分工明确

---

## 二、Source Discovery 策略

## 二、搜索策略：关键词精确化 + 分引擎路由

### 2.1 引擎路由（关键）

该 SearXNG 实例的不同 `categories` 参数路由到不同后端引擎：

| categories 参数 | 后端引擎 | 适用场景 | 日期信息 |
|:---------------|:---------|:---------|:--------|
| `news` | Bing News | **英文新闻搜索（首选）** — 有时效、有来源、有相对时间 | ✅ `20 hours ago` |
| `general` | DuckDuckGo + 多引擎 | 中文搜索、百科补充、fallback | ❌ 通常无日期标记 |

**不要用 `general` 搜英文新闻** — 它返回 Wikipedia/Britannica 等百科内容，而非实时新闻。

### 2.2 语言路由

```
中文搜索 → categories=general + language=all
英文新闻 → categories=news + language=en
```

### 2.3 不要搜索宽泛关键词

❌ 错误：
```
马斯克
Elon Musk
```

✅ 正确：
```
Bill Gates     + categories=news + time_range=week
Elon Musk SEC  + categories=news + time_range=week
```

原因：SearXNG 对宽泛关键词返回百科/旧闻/泛化结果。
- `site:reuters.com Bill Gates` + `categories=general` → 3 条（均为不相关 Reuters 文章）
- `Bill Gates` + `categories=news` → 11 条（全部相关）

**结论：对该 SearXNG 实例，优先策略为：**
```
categories=news + 精确实体名          # 主要策略（有时效性）
categories=general + 精确实体名       # 补充策略（广覆盖，但含旧内容）
```

### 语言路由

| 源 | 中文 | 英文 |
|:---|:----|:----|
| **SearXNG** | ✅ 直接搜中文 | ✅ 直接搜英文 |
| **Tavily** | ❌ 需翻译成英文 | ✅ 直接搜英文 |

---

## 三、按来源分类（Source Matrix）

### S 级 — 官方 / 监管（最高优先级）
| 来源 | 说明 |
|:----|:-----|
| SEC | `site:sec.gov` |
| Federal Reserve | `site:federalreserve.gov` |
| NASA | `site:nasa.gov` |
| White House | `site:whitehouse.gov` |
| 法院 | `site:uscourts.gov` |
| NHTSA | `site:nhtsa.gov` |
| 公司 IR | `site:tesla.com/ir` |

### A 级 — 通讯社（高可信）
| 来源 | 说明 |
|:----|:-----|
| Reuters | `site:reuters.com` |
| AP | `site:apnews.com` |
| Bloomberg | `site:bloomberg.com` |

### B 级 — 财经/综合
| 来源 | 说明 |
|:----|:-----|
| CNBC | `site:cnbc.com` |
| FT | `site:ft.com` |
| WSJ | `site:wsj.com` |
| The Hill | `site:thehill.com` |
| Politico | `site:politico.com` |
| The Guardian | `site:theguardian.com` |

### C 级 — 科技 / 行业
| 来源 | 说明 |
|:----|:-----|
| TechCrunch | `site:techcrunch.com` |
| The Verge | `site:theverge.com` |
| Ars Technica | `site:arstechnica.com` |
| Space.com | `site:space.com` |
| Electrek | `site:electrek.co` |

### D 级 — 社区 / 补充
| 来源 | 说明 |
|:----|:-----|
| X/Twitter | 通过 Tavily 或浏览器 |
| GitHub | `site:github.com` |
| Reddit | `site:reddit.com` |

---

## 四、SearXNG HTML 字段提取指南

该 SearXNG 实例的 HTML 输出**没有 `datetime` 属性**。日期信息嵌入在 `<div class="highlight">` 的相对时间中。

### News 类别可提取字段

| 字段 | 提取方式 | 示例 |
|:-----|:---------|:-----|
| **标题** | `<h3><a>` text | "Bill Gates Tells Congress..." |
| **URL** | `<a class="url_header">` href | `https://yahoo.com/...` |
| **域名** | `<span class="url_i1">` | `https://www.yahoo.com` |
| **路径** | `<span class="url_i2">` | `› news › politics › ...` |
| **摘要** | `<p class="content">` | "Congress wanted to speak with..." |
| **来源** | `<div class="highlight">` 中 `|` 右侧 | "Yahoo" |
| **相对时间** | `<div class="highlight">` 中 `|` 左侧 | "20 hours ago" |
| **缩略图** | `<img class="thumbnail">` src | Bing CDN URL |
| **搜索引擎** | `<div class="engines"><span>` | "bing news" |
| **缓存链接** | `<a class="cache_link">` href | Wayback Machine URL |

### General 类别 vs News 类别差异

| 特征 | News | General |
|:-----|:-----|:--------|
| **缩略图** | ✅ `<img class="thumbnail">` | ❌ 无 |
| **来源/时间** | ✅ `<div class="highlight">` | ❌ 无（百科类完全无时间） |
| **典型内容** | 时效性新闻 | 百科/Britannica/Forbes简介 |
| **主引擎** | Bing News | DuckDuckGo |

### 相对时间转绝对日期

```python
import re
from datetime import datetime, timedelta

def parse_relative_time(text: str, now: datetime = None) -> str:
    """'20 hours ago' → '2026-06-27 22:00'"""
    if not now:
        now = datetime.now()
    m = re.search(r"(\d+)\s*(hour|day|minute)s?\s*ago", text.lower())
    if not m:
        return ""
    n, unit = int(m.group(1)), m.group(2)
    if "hour" in unit:
        dt = now - timedelta(hours=n)
    elif "day" in unit:
        dt = now - timedelta(days=n)
    elif "minute" in unit:
        dt = now - timedelta(minutes=n)
    else:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")
```

### General 类别防旧内容过滤

`categories=general` 返回的结果可能包含无日期百科/简介（Wikipedia、Britannica、Forbes Profile 等）。过滤策略：

```python
STALE_DOMAINS = ["wikipedia.org", "britannica.com", "forbes.com/profile"]
# 过滤：URL 含上述域名 → 降级或排除
```

---

## 五、搜索前加入时间过滤

❌ 错误（等 AI 后面过滤）：
```
Elon Musk
```

✅ 正确（搜索前过滤）：
```
# SearXNG 用 time_range 参数
time_range=day|week|month|year

# Tavily 用 days 参数
"days": 3
```

---

## 六、搜索流水线（Pipeline）

```
Stage 1: SearXNG Source Discovery
├── 向 10-20 个白名单来源发送查询
├── 每个来源搜 1-3 个实体关键词
├── 使用 categories=news（主要）+ categories=general（补充）
├── URL 空格必须用 + 编码
├── 得到 50-80 条原始结果（标题+URL+相对时间）
├── 相对时间 → 绝对日期转换
└── 保存到临时缓存

Stage 2: 事件聚类 + 可信度评分
├── 去重（相同事件合并，title[:50] 去重）
├── 按信源权威性打分
│   ├── 官方来源     +40
│   ├── 通讯社       +35
│   ├── 财经         +30
│   ├── 科技         +20
│   ├── 旧内容       -40（Wikipedia/Britannica/Forbes Profile）
│   └── 论坛         -50
├── 排除无日期旧内容
└── 聚类为 A/B/C 三级事件

Stage 3: 正文提取（仅 A 级）
├── 对 A 级事件（5-10 条）
├── 用 browser 或 web_extract 获取全文
└── 保存原文+元数据

Stage 4: Tavily Deep Analysis（仅 A 级）
├── 对 A 级事件
├── 参数: search_depth=advanced, include_raw_content=True, topic=news, days=7
└── 获取 AI 摘要 + 多源交叉验证

Stage 5: 证据矩阵 + 报告生成
├── Cross Validator（多源验证表）
├── Evidence Builder（证据链）
└── Media Intelligence Report
```

---

## 七、预算控制器（重要）

```
SearXNG → 无限使用（免费自托管）
   ↓
得到 80 条原始结果
   ↓
可信度评分 + 去重 → Top 15（A 级 5-10 + B 级 5）
   ↓
Tavily → 仅对 Top 15 调用（每次 1-2 次搜索）
   ↓
SearXNG 承担 70-80% 检索
Tavily 承担 20-30% 深度分析
```

---

## 八、缓存策略

| 缓存类型 | 有效期 | 说明 |
|:---------|:-------|:-----|
| 搜索缓存 | 48 小时 | 同一来源+同一实体+同一时间范围 → 直接复用 |
| 事件缓存 | 24 小时 | 同一事件已生成报告 → 直接复用 |
| 正文缓存 | 7 天 | 已提取的文章全文 → 不重复提取 |

---

## 九、高耦合事件分析框架

### 定义：满足任一条件即进入深度分析

| 标准 | 说明 |
|:----|:-----|
| **法律/监管** | 涉及法院、SEC、政府调查、诉讼 |
| **重大财务** | 十亿美元级交易、股价波动、指数纳入 |
| **核心技术** | FSD、Starship、新模型发布、安全关键 |
| **政治/社会** | 政府任命、政策影响、国际关系 |
| **内部变动** | 高管离职、大规模裁员、组织重组 |

### 深度分析结构（每项 800-1500 字）

```
### 4.x [项目名称]
- **事件概述** — 一句话概括
- **时间线** — 时间表
- **多方信源对比** — 来源对比表
- **影响评估** — 法律/财务/声誉/监管四大维度
- **风险点** — 关键不确定性和待核实项
```

---

## 十、交叉验证协议

| 状态 | 含义 | 要求 |
|:----|:-----|:-----|
| ✅ **多源一致** | 2+ 独立信源确认 | 可视为事实 |
| ⚠️ **单源/独家** | 仅 1 家媒体报道 | 标注低可信度 |
| ❌ **矛盾** | 信源之间不一致 | 需单独排查 |

Source classification:
| 等级 | 标准 |
|:----|:------|
| 🔴 **一级** (Primary) | 通讯社/官方文件（Reuters, AP, SEC） |
| 🟢 **二级** (Secondary) | 主流媒体（CNN, NYT, Guardian, CNBC, Bloomberg） |
| 🟡 **三级** (Tertiary) | 分析/评论/博客/独家单源 |

---

## 十一、报告模板

```
## 一、执行摘要（300字以内）
   核心事件数 | 高耦合项目数 | 关键结论

## 二、直接言论清单（按时间倒序）
   | 时间 | 平台 | 原文/摘要 | 上下文 | 信源级别 |

## 三、事件总览表（按业务线分类）
   | 业务线 | 事件 | 关键媒体 | 日期 | 信源级别 | 交叉验证状态 |

## 四、高耦合度项目深度分析
   ### 4.x [项目名称] — 800-1500字

## 五、交叉验证结论
   - ✅ 多源一致确认项
   - ⚠️ 独家/单源披露项
   - ❌ 矛盾信息/待核实项

## 六、信息盲区与建议
   - 本次搜索未能覆盖的潜在信息
   - 建议后续跟踪的时间节点

## 七、搜索流水线复盘
   Stage 统计（查询数/命中数/调用次数/耗时）
   改进建议
```

---

## 九、报告格式模板

当需要输出正式媒体情报报告时，按以下结构组织：

```
# 标题 — 时间段分析报告

## 一、执行摘要（300字以内）
   核心事件数 | 高耦合项目数 | 关键结论

## 二、直接言论清单（按时间倒序）
   | 时间 | 平台 | 原文/摘要 | 上下文 | 信源级别 |

## 三、事件总览表（按业务线分类）
   | 业务线 | 事件 | 关键媒体 | 日期 | 信源级别 | 交叉验证状态 |

## 四、高耦合度项目深度分析（每项800-1500字）
   ### 4.x [项目名称]
   - 事件概述
   - 时间线
   - 多方信源对比
   - 影响评估（法律/财务/声誉/监管）
   - 风险点

## 五、交叉验证结论
   - ✅ 多源一致确认项
   - ⚠️ 独家/单源披露项（标注风险）
   - ❌ 矛盾信息/待核实项

## 六、信息盲区与建议
   - 本次搜索未能覆盖的潜在信息
   - 建议后续跟踪的时间节点
```

## 九、搜索前工作流（用户偏好）

本用户要求在搜索开始前**先输出实施方案**，经确认后再执行。不要跳过此步骤直接搜索。

```
① 输出《X 搜索实施方案》
   ├── 搜索策略（SearXNG/Tavily 分工）
   ├── Source Matrix（实体+来源白名单）
   ├── 高耦合度定义标准
   └── 输出格式预览
② 用户确认 ✅
③ 执行完整搜索
④ 生成报告
```

## 十、输出格式规范（用户要求）

### 报告结构（用户指定）

```
# 一、执行摘要（300字以内）
# 二、直接言论清单（按时间倒序）
   | 时间 | 平台 | 原文/摘要 | 上下文 | 信源级别 |
# 三、事件总览表（按业务线分类）
   | 业务线 | 事件 | 关键媒体 | 日期 | 信源级别 | 交叉验证状态 |
# 四、高耦合度项目深度分析（每项800-1500字）
# 五、交叉验证结论
# 六、信息盲区与建议
```

### 关键原则
- 每条信息**必须注明来源 + 发布日期**
- 必须做**交叉验证**（多源一致 / 单源待核实 / 矛盾标记）
- **假新闻/未核实信息**必须标注（如 C 级事件标注"可能不实"）
- 报告开头必须有**执行摘要**

## 十一、关键原则（Pitfalls）

- ⚠️ **不要搜宽泛关键词** — SearXNG 不是 Google
- ⚠️ **不要 Tavily 扫全量** — 只给 A 级事件
- ⚠️ **不要等 AI 过滤时间** — 搜索前就用 `time_range` 和 `days`
- ⚠️ **不要重复搜索** — 48 小时缓存
- ⚠️ **SearXNG JSON API 可能已禁用** — 该实例只返回 HTML，需 HTML 解析
- ⚠️ **Tavily 中文搜索无效** — 中文搜索前必须翻译成英文
- ⚠️ **去重是关键的** — Tavily 跨查询返回重复项，用 `title[:50]` 去重
- ⚠️ **General 类别含旧内容** — Wikipedia/Britannica/Forbes 简介需过滤
- ⚠️ **SearXNG URL 空格用 +** — `q=Bill Gates` → 0 结果；`q=Bill+Gates` → 正常
- ⚠️ **SearXNG 超时设置** — curl timeout >= 25s

## 十三、参考文件

- `references/rss-source-matrix.md` — 72 源 RSS 订阅清单（按 8 大类组织，skill 文档级参考）
- `references/rss-system.md` — **已部署的 RSS 扫描系统**（98 源，cron 每 5 分钟调度，SQLite + Wiki 存储，网络路由策略，字段定义，调用方式）
- `references/searxng-html-parsing.md` — SearXNG HTML 字段提取参考
