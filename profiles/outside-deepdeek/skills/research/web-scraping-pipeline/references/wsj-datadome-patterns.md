# WSJ DataDome 反爬行为记录

站点评级: **DataDome — 当前最高级反爬**

## 已验证的工具表现

| 工具/策略 | 主页面(livecoverage) | 子卡片(card/) | 单篇文章(/articles/) |
|-----------|:--------------------:|:-------------:|:-------------------:|
| `web_extract` 直连 | ✅ 成功 | ❌ DataDome | ❌ DataDome |
| Scrapling StealthyFetcher | ❌ HTTP 401 | ❌ 401 | ❌ 401 |
| Scrapling Fetcher(requests) | ❌ 超时/无响应 | ❌ 超时 | ❌ 超时 |
| Playwright (patchright) | ❌ "Please enable JS and disable ad blocker" | ❌ 同上 | ❌ 同上 |
| Wayback Machine 存档 | ✅ 已存档内容 | ✅ 已存档内容 | ✅ 已存档内容 |
| 搜索摘要补充 | ✅ 片段可用 | ✅ 片段可用 | ❌ 无片段 |

## URL 年份陷阱 (V1 规则触发案例)

WSJ live blog URL 复用跨年 slug 模式：
- `.../stock-market-today-{topic}-06-30-2025` ← 内容可能是 2026 年的
- `.../stock-market-today-{topic}-06-30-2026` ← 内容是 2026 年当天的

**触发事件**：2026-06-30 晚上搜索 WSJ，第一条结果是 `06-30-2025` 路径但描述写 "June 30, 2026"。使用 Wayback Machine 提取成功，但内容是"昨天"（周一收盘）而非"今天"（周二盘前）。

**根因**：
1. 未执行 URL.year vs content.year 校验
2. 未检查搜索摘要中的 `Last Updated: June. 30, 2025 at 9:44pm ET`
3. 默认取了第一条结果而非对比 `2025` vs `2026` 两条候选URL

## 已验证的有效提取策略

### 策略 A: 主 live blog 页面（当日/实时）

```
web_extract(urls=["https://www.wsj.com/livecoverage/stock-market-today-{topic}-{MM-DD-YYYY}"])
→ 可获取 lead article + 卡片标题摘要
```
- 先执行 V1 时间校验：确认 URL 中的年份与 Last Updated 年份一致
- 子卡片内容需另寻补充途径

### 策略 B: 已归档的历史页面

```
web_extract(urls=["https://web.archive.org/web/{YYYYMMDDHHMMSS}/https://www.wsj.com/..."])
```
- 单篇文章、live blog 卡片均可获取
- 仅对已存档内容有效（今日内容可能未存档）
- 使用后标注 `数据来源: 历史快照`

### 策略 C: 搜索摘要补充

当 A 和 B 均不可行时，通过 `web_search` 获取卡片片段：
```
web_search(query='WSJ "卡片标题" "June 30 2026"')
```
- 搜索摘要包含文章首段或核心描述
- 可用于拼凑文章大意
