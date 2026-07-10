# search-engine-v2 独立化重构 — 设计决策记录

> 2026-07-08 重构: 从 "Agent 编排壳" 变为 "独立可运行引擎"

## 问题诊断

v2.0 所有抓取策略（direct/archive/scrapling/browser）都是 `Callable` 占位符，
需要 Agent 会话注入 Hermes 工具函数。批量抓取 100 篇新闻时：
- 每篇都要跑一次 Agent/LLM 会话 → 成本不可接受
- browser_navigate/computer_use 假设可交互环境 → cron 不可用
- 天然串行/交互式 → 不适合批处理

## 解决方案

### 1. 真实网络实现 (`core/fetchers.py`)

每个策略都有独立 Python 实现：

| 策略 | 实现 | 依赖 | 成本 |
|------|------|------|:--:|
| direct | httpx + trafilatura | httpx, trafilatura | 1 |
| google_cache | webcache.googleusercontent.com | httpx | 1 |
| archive | web.archive.org/web/0/{url} | httpx | 1 |
| scrapling | Scrapling StealthyFetcher | Scrapling (可选) | 2 |
| browser | Playwright headless | Playwright (可选) | 3 |
| search_snippet | 搜索API (外部注入) | 用户提供 | 1 |

### 2. 代理路由

境外域名自动走代理，国内域名直连：

```
_is_chinese_domain(url):
  .cn / .com.cn / .org.cn → 直连
  人民网/新华网/央视等20个白名单 → 直连
  其他 → HTTPS_PROXY (127.0.0.1:10808)
```

与 RSS 扫描器的分流逻辑一致。

### 3. 纯脚本结构化抽取 (`core/extractor.py`)

零 LLM 依赖，100 篇 < 0.1 秒：

- 标题: Markdown H1 → 首行文本
- 日期: URL路径 → ISO时间戳 → "Published"行 → 中文"X年X月X日" → 当天兜底
- 作者: 前300字符 byline 正则 (By/Reporting from/| Author)
- 摘要: 前2-3句有意义文本
- 要点: 信号词 + 统计数据 + 实体动作 → 加权排序取top 5

### 4. 可配置阈值 (`config/settings.py`)

所有硬编码常量外提:
- `min_content_len` (全局200, 域名级可覆盖)
- 超时: direct 30s, scrapling 45s, browser 60s
- 限速: 默认1s/域名, 友好域名0.5s
- 并发: ThreadPoolExecutor 默认4 workers

### 5. 双模式共存

```
Agent 模式 (router.py)        Standalone 模式 (batch.py)
─────────────────────────     ──────────────────────────
工具注入 → HermesToolbox       真实实现 → fetchers.py
场景: 交互式, 用户点击触发      场景: cron, 批量无人值守
```

共享: domain_profiles.py, temporal.py, cascade.py, extractor.py

## 发现并修复的问题

### archive URL 格式错误

**问题**: `https://web.archive.org/web/{url}` → 404
**修复**: `https://web.archive.org/web/0/{url}` (0=最新快照)

### Scrapling StealthyFetcher 超时

**问题**: Bloomberg 上 StealthyFetcher (patchright+Chromium) 30ms 即超时
**结论**: 浏览器模式不稳定，保留但标记 known_failing

### 作者提取误匹配

**问题**: 在 1500 字符范围内搜索 → 匹配到正文引述 ("sick people and they're vicious")
**修复**: 限制搜索范围到前 300 字符 + 黑名单过滤

### BBC 日期缺失

**问题**: BBC 使用相对时间 ("Published 7 hours ago")
**修复**: 无绝对日期时默认当天 UTC 日期（RSS 新闻场景合理）

## 成本模型

| 规模 | 改造前 (全LLM) | 改造后 (脚本优先) |
|------|:--:|:--:|
| 10 篇 | $0.02 / 30s | $0 / 0.01s |
| 100 篇 | $0.20 / 5min | $0 / 0.08s |
| 1000 篇 | $2.00 / 50min | $0 / 0.8s |

LLM 仍可通过 `--llm-extract` 按需启用，用于需要语义理解的边缘 case。
