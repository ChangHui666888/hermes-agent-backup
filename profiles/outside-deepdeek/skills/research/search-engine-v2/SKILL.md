---
name: search-engine-v2
description: 搜索抓取引擎v2 — 域名画像 + 级联抓取 + 脚本抽取 + 五维评分 + 智能路由 + 三级增强。全链路优先脚本，LLM按需介入。
tags:
  - search
  - scraping
  - web-scraping
  - domain-profile
  - cascade
  - temporal-validation
  - multi-source-merge
  - entity-driven
  - cost-trace
  - wsj
  - paywall-bypass
  - news-intelligence
  - scoring
  - llm-router
  - qwen3
  - deepseek
  - proxy-routing
category: research
---

# 搜索抓取引擎 v2（2026-07-08 独立化重构）

## 🆕 v2.2: News Intelligence Engine（评分 + 路由 + 三级增强）

`news_intel/` 子系统实现从"抓全文"到"判断价值→按价值分流处理"的升级：

```\nRSS → 五维评分(0-100) → Tier C(<60): Python规则 → Tier B(60-89): Qwen3本地 → Tier A(≥90): DeepSeek Flash\n```\n\n**五维评分引擎** (`news_intel/scorer.py`):\n- Source Authority (20, 上限20) — 来源权威度，70+源预配置\n- Event Impact (30, 上限30, 同类取最高不累加) — 关键词匹配，5领域\n- Entity Importance (20, 上限20) — 实体权重库（公司/人物/国家）\n- Market Relevance (20, 上限20) — 资产影响图谱（20+资产链）\n- Velocity (10, 上限10) — Jaccard 0.5 标题指纹聚类 + 30min时间窗口\n- **Total 硬上限 100**

**三层增强器** (`news_intel/enhancers.py`):
- Tier C: `enhance_python()` — 零成本规则（标签/实体/摘要）
- Tier B: `enhance_qwen()` — Qwen3-1.7B 本地（LM Studio, 60s超时, max_tokens=1024, 单次合并 prompt）
- Tier A: `enhance_deepseek()` — DeepSeek V4 Flash 深度分析（事件/影响/市场信号/风险）

实测 60 篇 RSS (2026-07-10): Tier A (≥90) ~1%, Tier B (60-89) ~10%, Tier C (<60) ~89% — 接近零成本。
评分维度有硬上限（Event Impact 命中多30分词仍只计30），Total ≤ 100。
详见 `references/news-intel.md`。

## 🆕 v2.1 关键变化：从"Agent 编排壳"→"独立可运行引擎"
详见 `references/news-intel.md`。

v2.0 的问题：所有抓取策略（direct/archive/scrapling/browser）都是 `Callable` 占位符，
需要 Agent 会话注入 Hermes 工具函数才能工作。**批量抓取时每篇文章都要跑一次 Agent/LLM 会话，
成本和延迟不可接受。**

v2.1 解决方案：
- **新增 `core/fetchers.py`** — 所有策略的真实 Python 实现（httpx+trafilatura / Scrapling / Playwright / wayback machine）
- **新增 `core/rate_limiter.py`** — 域名感知令牌桶限速，批量抓取不封 IP
- **新增 `config/settings.py`** — 可配置阈值（MIN_CONTENT_LEN、超时、并发数等）
- **新增 `scripts/batch.py`** — 独立 CLI 入口，`python batch.py --urls urls.txt --out results.jsonl`
- **新增 `core/base.py → StandaloneEngine`** — 程序化 API，`engine.extract(url)` / `engine.batch_extract(urls)`
- **保留全部 Agent 模式** — `router.py` + `demo.py` 仍然 100% 可用，两种模式共享同一套 domain_profiles / cascade / temporal 纯算法层

## 双模式架构

```
                    ┌──────────────────────────────┐
                    │   config/domain_profiles.py   │  ← 17 域名画像（共享）
                    │   core/temporal.py            │  ← 时间一致性校验（共享）
                    │   config/settings.py          │  ← 可配置阈值（共享）
                    └──────────┬───────────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            │                                      │
    ┌───────┴────────┐                   ┌────────┴──────────┐
    │  Agent 模式     │                   │  Standalone 模式   │
    │  (router.py)   │                   │  (batch.py)       │
    ├────────────────┤                   ├───────────────────┤
    │ 工具注入:       │                   │ 真实网络实现:       │
    │ web_extract     │                   │ fetch_direct()     │
    │ web_search      │                   │ fetch_archive()    │
    │ browser_navigate│                   │ fetch_scrapling()  │
    │ llm_extract     │                   │ fetch_browser()    │
    │ delegate_task   │                   │ RateLimiter        │
    ├────────────────┤                   ├───────────────────┤
    │ 场景: 交互式     │                   │ 场景: cron/批量     │
    │ 用户点击触发抓取  │                   │ ThreadPoolExecutor │
    │ 低频单条请求     │                   │ 无人值守批量抓取    │
    └────────────────┘                   └────────────────────┘
```

## 关键改进（vs v1）

| 改进 | 说明 |
|------|------|
| **域名画像知识库** | domain_profiles.py — 每个域名预配置反爬级别、最优策略顺序、已知必败工具 |
| **成本感知级联** | cascade.py — 先查画像 → 剪枝必败工具 → 逐级尝试成功即停 |
| **可观测性** | 每次调用返回 `cost_trace` + `total_cost` |
| **并行抓取** | s05_parallel — delegate_task 多URL并行 |
| **多源融合** | s06_merge — LLM 交叉验证共识/分歧 |
| **时间校验 v2** | temporal.py — freshness_mode 感知（breaking/market/analysis/default） |
| **WSJ 时间戳修复** | s04_wsj.py 正则支持 MM-DD-YYYY 格式（live blog URL 如 06-30-2025） |

## 域名画像表（已收录 17 个域名）

| 域名 | 反爬级别 | 策略顺序 | 已知必败 |
|------|---------|---------|---------|
| wsj.com | datadome | direct → google_cache → archive → search_snippet | scrapling, browser |
| bloomberg.com | datadome | direct → google_cache → archive → search_snippet | scrapling, browser |
| ft.com | datadome | direct → google_cache → archive → search_snippet | scrapling, browser |
| nytimes.com | soft_paywall | direct → archive → search_snippet | — |
| washingtonpost.com | soft_paywall | direct → archive → search_snippet | — |
| cnbc.com | cloudflare | direct → scrapling → archive → search_snippet | — |
| businessinsider.com | cloudflare | direct → scrapling → archive → search_snippet | — |
| reuters.com | none | direct | — |
| apnews.com | none | direct | — |
| newsweek.com | none | direct → archive → search_snippet | — |
| aljazeera.com | none | direct | — |
| theguardian.com | none | direct | — |
| bbc.com | none | direct | — |
| bbc.co.uk | none | direct | — |
| cnn.com | none | direct | — |
| arxiv.org | none | direct | — |
| 未知域名 | unknown | 全梯度: direct→archive→scrapling→browser→computer→snippet | — |

## 策略梯度成本图（v2.1 已全部真实化）

```
策略         成本    实现                            Agent模式工具映射
─────────────────────────────────────────────────────────────────────────
direct        1     httpx + trafilatura             web_extract(url)
google_cache  1     Google Cache (webcache.google)   web_extract(cache_url)
archive       1     httpx → web.archive.org         web_extract(archive_url)
search_snippet 1    搜索API + snippet               web_search(url) → 第一条摘要
scrapling     2     Scrapling StealthyFetcher       scrapling_fetch(url)
browser       3     Playwright headless              browser_navigate(url)
computer_use  5     ❌ Standalone禁用 / Agent手动     computer_use(url)
```

### ⚡ 核心原则: 批量模式默认零 LLM

`batch.py` 默认走纯脚本规则抽取 (`core/extractor.py`)，0.78ms/篇。
只有显式传 `--llm-extract` 时才调用 DeepSeek。

> 设计决策详见: `references/architecture-v2.1.md`

| 函数 | 用途 | 依赖 |
|------|------|------|
| `fetch_direct(url, rate_limiter)` | 直接 HTTP GET + trafilatura 正文提取 | httpx, trafilatura |
| `fetch_google_cache(url, rate_limiter)` | Google 缓存快照（付费墙最优解） | httpx |
| `fetch_archive(url, rate_limiter)` | Wayback Machine 快照抓取 | httpx |
| `fetch_scrapling(url, rate_limiter)` | TLS指纹随机化绕过 Cloudflare | Scrapling (可选) |
| `fetch_browser(url, rate_limiter)` | Playwright 无头浏览器（JS渲染） | Playwright (可选) |
| `fetch_search_snippet(url, search_func)` | 搜索摘要兜底（唯一保留的外部注入） | 用户提供搜索函数 |
| `llm_extract_structured(content, prompt)` | DeepSeek API 结构化JSON抽取 | httpx + API key |
| `RateLimiter` | 域名感知令牌桶限速器 | 纯 Python |
| `extract_single(url, ...)` | 一站式：级联+LLM抽取+时间校验 | 以上全部 |

## 🆕 Hermes Cron 部署（⚠️ `once` vs `every` 陷阱）

**创建命令必须是 `"every 30m"`，不是 `"30m"`：**

```powershell
# ❌ 错误 — 只执行一次
hermes cron create "30m" --name news-pipeline ...
# → Schedule: once in 30m, Repeat: 0/1

# ✅ 正确 — 循环执行
hermes cron add "every 30m" --name news-pipeline --script news-pipeline.py --workdir "C:\Users\ChangHui\AppData\Local\hermes\scripts" --no-agent
# → Schedule: every 30m, Repeat: ∞
```

**当前推荐命令**:
```powershell
hermes cron add "every 5m"  --name rss-scan --script rss-scanner.py --workdir "C:\Users\ChangHui\AppData\Local\hermes\scripts" --no-agent
hermes cron add "every 30m" --name news-pipeline --script news-pipeline.py --workdir "C:\Users\ChangHui\AppData\Local\hermes\scripts" --no-agent
```

**Shell → Python 契约**: Shell 只 `dirname "$0"` 定位自己，启动同目录 Python。Python 用 argparse + logging，调用 `run_pipeline()`。**不要 `cd`、不要 `sys.path`、不要硬编码路径。**

**Report**: `run_pipeline()` 返回 dict → 写 `~/.hermes/news-pipeline-report.json` → Shell 读取打印摘要。格式见 `references/pipeline-report-format.md`。

**Fail-fast**: Qwen 首次超时全局跳过。Cloud push 使用批量推送 (`push_batch`)。已评分/已增强自动去重。

**日志**: `scripts/logs/news-pipeline.log`（完整 traceback）。PowerShell: `Get-Content .\logs\news-pipeline.log -Tail 50`。

详见 `references/cron-engineering-standards.md`、`references/pipeline-bugfixes.md` 和 `references/pipeline-optimizations.md`。

## ⚠️ 已知问题与规避

### Cron 超时 (120s 硬超时)

**现象**: `Script timed out after 120s`，日志无 pipeline 输出。

**根因和修复**:
1. Python 输出缓冲 → `PYTHONUNBUFFERED=1` + `flush=True`
2. Shell 脚本 `cd` 到 MSYS 路径失败 → 改用 `.py` 脚本
3. Qwen 3次调用×13s/篇 → **合并为1次调用** (`QMERGE_PROMPT`), max_tokens=1024, 60s超时
4. Cron 用 PowerShell 单行（不支持 `\` 换行）

**Fail-fast 机制**:
- Qwen: 首次超时 → 全局 `_qwen_available = False` → 跳过所有后续调用
- Cloud push: 连续3次失败 → break
- 去重: 已评分跳过 (`rss_raw`), 已增强跳过 (`LEFT JOIN WHERE nc.id IS NULL`)

```powershell
# 正确的 PowerShell cron 创建命令
hermes cron create --name news-pipeline --script news-pipeline.py --no-agent --repeat 99999 "30m" ""
```

### 评分效率决策（2026-07-10 benchmark）

三方案对比 200篇 RSS:
| 方案 | 耗时 | LLM调用 | 
|------|:--:|:--:|
| A: 先评分→选择增强 **(当前)** | 48s | 48次 |
| B: 评分+增强同步(全量) | 600s | 600次 |
| C: 先提取→后评分(全量) | 0.02s | 0次 |

**结论**: A 方案最优。评分只需 RSS 标题+摘要（<1ms/篇），LLM 增强仅触发 ~8% 的 Tier A/B 文章。切勿改为先提取后评分——评分不需要全文。

### Wayback Machine URL 格式（2026-07-08 修复）
**错误格式**: `https://web.archive.org/web/{url}` → 返回 404  
**正确格式**: `https://web.archive.org/web/0/{url}` → 重定向到最新快照  
已在 `cascade.py` 和 `fetchers.py` 中同步修复。

### 当日文章 WayBack 未归档
当天刚发布的付费墙文章（Bloomberg/WSJ/FT），Wayback Machine 可能还没有快照。
此时级联路径 `direct→403 → archive→404 → search_snippet→skip` 全部失败是**正常行为**，
不是引擎 bug。解决方案：等 24-48 小时后重试，或接入 Bloomberg 订阅 API。

### WSJ 时间戳格式
`s04_wsj.py` 的 `WSJ_DATE_RE` 只匹配 `/YYYY/MM/DD/` 格式，遗漏了 `06-30-2025` 格式的 live blog URL。已新增 `WSJ_DATE_ALT_RE` 正则修复。

### Scrapling / Playwright 为可选依赖
未安装时自动跳过（返回 None），级联引擎继续尝试下一个策略。大部分站点 `direct` + `archive` 已足够。

### 云端部署注意事项

**JSON 字段验证**: SQLAlchemy 将 `tags`/`entities`/`analysis` 存为 JSON 字符串时，Pydantic 需要 `field_validator(mode='before')` 自动解析：
```python
@field_validator('tags', 'entities', mode='before')
@classmethod
def parse_json_fields(cls, v):
    if isinstance(v, str):
        try: return json.loads(v)
        except: return v
    return v
```
否则 GET /news 返回 500 Internal Server Error。

**端口冲突**: 云主机可能已有服务（n8n/scrapling_mcp/searxng）占用 8000/8080。部署前 `ss -tlnp` 检查，在 `docker-compose.yml` 中调整映射。

**Docker 权限**: 用户需在 `docker` 组才能免 sudo 操作。

## 2026-07-01 全场景实测结果

| 场景 | 域名 | cascade 路径 | cost | 状态 |
|:----:|------|------------|:----:|:----:|
| WSJ文章 → archive | wsj.com | direct❌→archive✅ | 1 | ✅ |
| WSJ Live Blog 直连 | wsj.com | direct✅ | 1 | ✅ |
| query驱动 → Reuters | reuters.com | direct✅ | 1 | ✅ |
| Reuters直连 | reuters.com | direct✅ | 1 | ✅ |
| 实体追踪 Trump | 多源 | search→rank→extract | 1 | ✅ |
| Newsweek直连 | newsweek.com | direct✅ | 1 | ✅ |

## 2026-07-08 Standalone 首次实战（RSS→batch）

| 来源 | 域名 | cascade | 字数 | 状态 |
|------|------|---------|------|------|
| BBC | bbc.co.uk | direct✅ | 3,695 | ✅ |
| Al Jazeera | aljazeera.com | direct✅ | 4,454 | ✅ |
| Bloomberg | bloomberg.com | direct→403, archive→404 | — | ❌ 当日未归档 |

详见 [references/rss-pipeline.md](references/rss-pipeline.md).

## 🆕 代理路由（境外走代理，国内直连）

`core/fetchers.py` 内置域名感知代理路由：

```
url → _is_chinese_domain(url)?
        │
   ┌────┴────┐
   │ YES     │ NO
   ▼         ▼
 直连      走代理 (HTTPS_PROXY 环境变量)
(更快)    (默认 127.0.0.1:10808)
```

**国内域名匹配规则**：
- TLD 后缀：`.cn`, `.com.cn`, `.org.cn`, `.gov.cn`, `.edu.cn`, `.net.cn`
- 精确域名：`people.com.cn`, `xinhuanet.com`, `cctv.com`, `chinanews.com`, `chinadaily.com.cn`, `huanqiu.com`, `sina.com.cn`, `163.com`, `qq.com` 等 20 个

与 RSS 扫描器的分流策略一致，无需手动判断。

## 调用方式

### 方式 A：Agent 模式（交互式，保留原样）

```
# 场景1: 已知 URL → 让 Agent 调 web_extract
web_extract(urls=["https://www.reuters.com/..."])  # 一级提取
→ 失败则 web_extract(urls=["https://web.archive.org/web/{url}"])  # 二级降级
→ 失败则 web_search(query="site:wsj.com article title")  # 三级搜索摘要

# 场景2: query → 发现→排序→抓取
web_search(query="美联储利率 2026 site:reuters.com")
→ 候选打分（s02_rank.py）
→ web_extract(best_url)
```

### 方式 B：Standalone 批量模式（cron/无人值守，🆕）

```bash
cd scripts/

# 单个URL调试
python batch.py --url "https://reuters.com/article/..." --verbose

# 批量抓取（从文件）
python batch.py --urls important_urls.txt --out daily.jsonl

# 从stdin读取
echo "https://reuters.com/..." | python batch.py --stdin --out results.jsonl

# 批量+LLM结构化抽取（需DEEPSEEK_API_KEY环境变量）
python batch.py --urls urls.txt --out structured.jsonl --llm-extract

# cron友好（无进度条）
python batch.py --urls urls.txt --out /data/daily.jsonl --no-progress

# 调参：更激进的并发+更短的限速间隔
python batch.py --urls urls.txt --out results.jsonl --max-workers 8 --rate-delay 0.5 --min-content-len 100
```

### 方式 C：Python API（程序化调用，🆕）

```python
from core.base import StandaloneEngine

engine = StandaloneEngine(skip_expensive=True)

# 单URL
result = engine.extract("https://reuters.com/article/...")
print(result["ok"], result["strategy_used"], result["total_cost"])

# 批量（ThreadPoolExecutor并发）
results = engine.batch_extract(["url1", "url2", "url3"], max_workers=4)
for r in results:
    print(r["url"], "✅" if r["ok"] else f"❌ {r.get('error')}")

# 带LLM结构化
engine = StandaloneEngine(
    llm_api_key="sk-...",
    skip_expensive=True,
)
result = engine.extract("https://reuters.com/...")
print(result.get("structured"))  # JSON结构化数据
```

### 方式 D：纯算法逻辑（时间校验/排序，保留原样）

```bash
cd scripts/
python -c "
from skills.s02_rank import score_candidate
score = score_candidate({'url':'...', 'title':'...'}, query='美联储', current_year=2026)
"
python -c "
from core.temporal import validate_temporal
result = validate_temporal(url='...', title='...', published_at='2026-06-30T18:00:00Z')
print(result['confidence'])
"
```

### 部署注意事项

详见 [references/deployment-pitfalls.md](references/deployment-pitfalls.md)：
- Docker 绕过 UFW → DOCKER-USER 链白名单
- passlib/bcrypt 版本冲突 → hashlib 替代
- Qwen3 system 角色 400 → 只用 user role，30s 超时
- RSS 隔离 3次失败→30min，重置删 state.json
- Hermes cron PowerShell 单行 + `--repeat 99999` + 末尾 `""`

### 纯算法层（Agent + Standalone 共享）
- `scripts/config/domain_profiles.py` — 域名画像知识库（17个域名）
- `scripts/config/settings.py` — 🆕 可配置阈值（MIN_CONTENT_LEN、超时、并发等）
- `scripts/core/base.py` — HermesToolbox + BaseSkill + 🆕 StandaloneEngine
- `scripts/core/cascade.py` — 成本感知级联引擎（现已读取 config/settings.py）
- `scripts/core/temporal.py` — 时间一致性校验

### 🆕 Standalone 网络层（无需 Agent）
- `scripts/core/fetchers.py` — 所有策略的真实网络实现 + RateLimiter + 代理路由
- `scripts/core/extractor.py` — 🆕 纯脚本结构化抽取（标题/日期/作者/摘要/要点，0.78ms/篇）
- `scripts/batch.py` — 独立 CLI 入口（cron 友好）

### 🆕 News Intelligence 层（评分 + 路由 + 增强 + 云端推送）
- `scripts/news_intel/scorer.py` — 五维评分引擎
- `scripts/news_intel/router.py` — Intelligence Router（3路分流）
- `scripts/news_intel/enhancers.py` — 三层增强器（Python/Qwen3/DeepSeek）
- `scripts/news_intel/db.py` — 三表 SQLite schema
- `scripts/news_intel/sync.py` — RSS 同步脚本
- `scripts/news_intel/pipeline.py` — 主编排入口
- `scripts/news_intel/pusher.py` — 🆕 Hermes → 云端 FastAPI 推送器
- `scripts/news_intel/config/` — 4个评分配置 JSON

### 🆕 云端部署（FastAPI + Vue + PostgreSQL + Docker）
详见 `references/cloud-deployment.md`。项目代码: `scripts/news-intel-platform/`。

### Agent 模式 Skill 层
- `scripts/skills/__init__.py` — 所有 Skill 导出
- `scripts/skills/s01_discover.py` — 三级搜索发现
- `scripts/skills/s02_rank.py` — 多维度候选排序
- `scripts/skills/s03_extract.py` — 内容提取（级联 + 时间校验 + LLM结构化）
- `scripts/skills/s04_wsj.py` — WSJ 专用（DataDome知情规避 + 修复版时间戳正则）
- `scripts/skills/s05_parallel.py` — 并行批量抓取
- `scripts/skills/s06_merge.py` — 多源融合
- `scripts/skills/s07_entity.py` — 实体驱动追踪
- `scripts/router.py` — 总调度器
- `scripts/demo.py` — 8场景 Mock 演示

- `references/deployment-architecture.md` — 🆕 云端部署架构（Docker+安全加固+Hermes推送）

```python
# config/settings.py 关键参数
min_content_len: int = 200        # 低于此长度→判定为被拦截
direct_timeout: float = 30.0      # 直连超时
rate_limit_default_delay: float = 1.0   # 同域名最小间隔
batch_max_workers: int = 4        # ThreadPool 并发数
llm_max_input_chars: int = 8000   # 送LLM前截断长度

# 域名特殊配置
domain_rate_delay = {"reuters.com": 0.5, "apnews.com": 0.5}  # 友好域名加速
```
