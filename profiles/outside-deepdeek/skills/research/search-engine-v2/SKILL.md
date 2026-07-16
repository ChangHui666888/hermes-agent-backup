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

# 搜索抓取引擎 v4.4（2026-07-12 Event Registry 升级）

## 🆕 Web Intelligence Dashboard (V1) — Cloud Deployed

**CRITICAL DEPLOYMENT RULES**:
- Windows Hermes is development-only. **NEVER** run npm, docker build, docker compose locally.
- ALL builds happen on cloud VPS (100.107.117.23) via Docker.
- Verification via `curl localhost:80` on cloud host, NOT `localhost:3000` locally.
- Node.js is NOT installed on cloud — Docker provides the runtime.
- Do NOT recover old `news-intel-platform` containers (Vue.js + PG, frozen).
- Architecture: Pipeline (Windows) → SQLite file → Cloud (Docker) → Web.
- Two separate systems, connected only by the Event Registry SQLite file.
- Transfer pattern: tar project → paramiko SCP → SSH unzip → docker compose up.

### Deployment target
- Cloud host: `100.107.117.23` (administrator, Docker 29.5.3, Ubuntu 24.04)
- Project path: `/home/administrator/news-intel-web/`
- Old deployment: `/home/administrator/news-intel-platform/` (frozen, do NOT recover)
- Docker compose: 3 services (frontend: Next.js 16, backend: FastAPI, nginx: reverse proxy)

### Docker build pitfalls (Next.js 16 + Tailwind v4)
1. `@apply` directives in CSS may fail in Docker build — use pure CSS variables instead
2. Type errors for missing `.d.ts` (e.g. react-simple-maps) — set `typescript.ignoreBuildErrors: true` in next.config.ts
3. Pages using `useSearchParams()` must be wrapped in `<Suspense>` boundary
4. Use `npm install --legacy-peer-deps` not `npm ci` in Dockerfile (lockfile may be platform-specific)

### SQLite read-only volume mount (UNRESOLVED)
- Docker volume mount `:/data:ro` prevents SQLite from creating WAL journal files
- Error: `sqlite3.OperationalError: unable to open database file`
- Next session fix: either remove `:ro` mount flag or use `?mode=ro&immutable=1` URI

See `references/web-v1-cloud-deployment.md` for full deployment guide.

## 🆕 V4.4: Event Registry + Source/Entity ID + Evidence/SourceChain/Timeline + Event API + Event-level LLM

## 🆕 v2.2: News Intelligence Engine（评分 + 路由 + 三级增强）

`news_intel/` 子系统实现从"抓全文"到"判断价值→按价值分流处理"的升级：

```
RSS → 五维评分(0-100) → Tier C(<60): Python规则 → Tier B(60-89): Qwen3本地 → Tier A(≥90): DeepSeek Flash
```

### 📐 架构 & Schema 文档

| 文件 | 内容 |
|------|------|
| `news_intel/architecture.html` | 5层宏观架构图 (Layer 0→5, SVG) |
| `news_intel/detail-flow.html` | **详细业务流程图** — 双模式(A/B) + 每步依赖标注 + 启用状态 |
| `news_intel/io-fields.html` | **各阶段输入/输出字段逐表追踪** — 所有字段名可从代码 grep 确认 |
| `news_intel/SCHEMA.md` | 21字段完整 JSON Schema + 置信度公式 + Action 枚举 |
| `references/io-field-trace.md` | 全阶段字段逐表追踪 (6个Phase, 每个字段的代码位置) |
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

## 🆕 Pipeline 运维 & 诊断

### 数据缺口根因诊断

三层数据缺口（RSS→Pipeline→Content→正文）的快速诊断流程，
含常见根因（content_md='' vs NULL 陷阱、占位行阻塞、200 LIMIT 瓶颈）和修复 SQL。
详见 `references/pipeline-gap-diagnosis.md`。

### pipeline_check.py 快速诊断

```bash
cd scripts/news_intel && python pipeline_check.py check
# 输出: RSS → PASS/FAIL, Pipeline → PASS/FAIL, Fetcher → PASS/FAIL
```

### 清理空占位行

```bash
python -c "
import sqlite3
db = sqlite3.connect('news_intel/news_intel.db')
deleted = db.execute(\"DELETE FROM news_content WHERE (content_md IS NULL OR content_md = '') AND (fetch_strategy IS NULL OR fetch_strategy = '')\").rowcount
db.commit(); print(f'Deleted {deleted} empty placeholder rows')
db.close()
"
```

### content_md = '' vs NULL 陷阱

备经验：`content_md IS NULL` 不会匹配 content_md = ''（空字符串）。
所有 WHERE 条件必须同时检查二者：
```sql
WHERE content_md IS NULL OR content_md = ''
```

## Hermes Cron 部署（⚠️ `once` vs `every` 陷阱）

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

### Hermes Cron 关键陷阱 🆕

```powershell
# ❌ 只执行一次 — Once in 30m, Repeat: 0/1
hermes cron create "30m" ...

# ✅ 循环执行 — Every 30m, Repeat: ∞
hermes cron add "every 30m" ...
```

`hermes cron create "30m"` 创建的是 "once in 30m"（30分钟后执行一次），不是 "每30分钟"。

### Cron 日志位置

```powershell
# 详细日志（含 traceback）
Get-Content C:\Users\ChangHui\AppData\Local\hermes\scripts\logs\news-pipeline.log -Tail 50

# Cron 运行记录
dir C:\Users\ChangHui\AppData\Local\hermes\cron\output\<job_id>\
```

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
- **RSS 隔离 3次失败→30min，重置删 state.json**
- **RSS 截断日期 "Fri, 10 Ju" → `email.utils.parsedate_to_datetime` 兜底**
- **Hermes cron PowerShell 单行 + `--repeat 99999` + 末尾 `""`**

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

## 🆕 L8 事件聚合器 V4.4 (`news_intel/aggregator.py`) — 当前生产版本

**V4.4 (2026-07-12)**。v4.3 基础上新增三层基础设施:

### Event Registry (Phase 3.5)
- `event_registry` 表 — 事件持久化 (event_id PK, 25+字段)
- `source_registry` 表 — 来源实体化 (source_id, name, type, authority)
- `entity_registry` 表 — 实体标准化 (entity_id, canonical_name, aliases, type)
- 聚合完成后自动写入，`_get_persist_db()` 单连接复用

### Source Entity ID + Entity ID
- `_source_name_to_id("Reuters")` → `SRC_REUTERS`
- `_entity_name_to_id("United States")` → `CTRY_UNITED_STATES`
- 前缀规则: COMP_ / PERS_ / CTRY_ / ORG_ / LOC_ / ENT_
- `_infer_source_type_from_name()`: GOVERNMENT / MEDIA / RESEARCH / SOCIAL

### Event Dossier 新字段 (3个)
- **evidence** [{quote, source, url}] — 原文摘录 (来自 article description)
- **source_chain** [{source_id, source_name, time, role(break|follow), url}] — 首发/跟进链
- **timeline** [{time, update, source}] — 按小时去重的关键节点

### Event API (pusher.py v4.4)
- `push_events()` → POST `/internal/events/batch` → 云端 PostgreSQL
- `push_from_registry()` → 从本地 event_registry 读取并推送
- `_event_to_push_format()` → 21字段 → 云端友好格式

### Event-level LLM (generator.py v4.4)
- `generate_intel()` — 用完整 Dossier 调用 DeepSeek 做 intelligence 分析
- `EVENT_INTEL_PROMPT` — significance / forecast / key_uncertainty / risk_level
- `_format_event_dossier()` — SAO + evidence + timeline + source_chain → LLM 可读文本
- `generate_for_event()` — 自动路由: 有 evidence → event-level, 否则 → 旧 insight

详见 `references/event-aggregation-v4.4.md`。

## 🗄️ V4.3 Event Schema (向后兼容参考)

V4.3 的 21 字段在 V4.4 中全部保留，新增 `evidence`, `source_chain`, `timeline` 三个字段，以及 SAO 中的 `entity_id` 和 source 中的 `primary_source_id`。

**V4.3 (2026-07-11 冻结)**。Event-Centric 3-phase + Entity Intelligence Layer + Location 硬约束 + Action 计数排序。

**核心规则** (`aggregator.py:300-348`, `fingerprint_score`):

| 维度 | 分值 | V4.3 变化 |
|------|:--:|------|
| Location 硬约束 | 阻断 | country不同 → return 0 |
| Anchor 完全匹配 | 100 | `subject|action|object|topic` 全等 |
| Action 相同 | +25 | OTHER除外 |
| Subject 相同 | +10~25 | **按稀有度加权** (subject_weight) |
| Object 相同 | +10~30 | **按稀有度加权** (object_weight) |
| Primary Topic 相同 | +10 | |
| Event Type 相同 | +10 | |
| Participants 交集≥2 | +10 | bonus only |
| Participants 交集=1 | +5 | bonus only |

**三阶段阈值**: EVENT_THRESHOLD=50, MERGE_THRESHOLD=75, 时间窗口=24h。

**V4.3 P0/P1/P2 关键修复** (vs V4.2.1):
1. `_detect_action` 改为**计数排序**（非首次命中）— 解决 ATTACKS 抢走 CEASEFIRE/NEGOTIATES 的 bug
2. Tehran 重复 key 移除 — 解决 country 精确比较静默拒绝合并
3. DIES 正则补全 (`assassinat(?:ed?|es?|ion)|killing|mourning`) — 解决死亡类新闻误判 ATTACKS
4. Hub dampening — 高频实体(>15%且≥5次)降权70%但不禁用 + MIN_SUBJECT_WEIGHT=0.15
5. Coherence 一致性校验 — 低一致性簇禁止评 HIGH
6. **Frozen Event Schema** — 21字段输出（见下节）

**Entity Intelligence Layer** (继承 V4.2):
- Entity Alias V2 — 54映射 (White House→US Government, Kremlin→Russian Gov, Pentagon→US DoD)
- Entity Type Weight — Country=1.0, Gov=1.0, Military=1.0, Org=0.8, Company=0.8, Person=0.5
- Topic IDF — `type_weight × (0.2 + 0.4 × global_idf + 0.4 × topic_idf)`
- Action Hierarchy — 21种动作 (SUES/ACCUSES/ATTACKS/CEASEFIRE/PEACE_DEAL/NEGOTIATES/...)
- 12类 Topic (Legal/Military/Diplomacy/Economic/Finance/Politics/Technology/Energy/Health/Sports/Leadership/Disaster)

**审计命令**:
```bash
python test_aggregator.py --hours 24 --window 6 --limit 100                  # 事件列表+新Schema
python test_aggregator.py --hours 24 --window 6 --limit 20 -v                # 完整指纹+评分矩阵(含IDF)
python test_aggregator.py --hours 24 --window 6 --limit 20 --single 1        # 单事件深度分析
python test_aggregator.py --hours 24 --window 6 --limit 20 --single 1 --insight  # +LLM洞察
```

⚠️ `--single N` 模式输出**真实聚类指纹**（test_aggregator.py 已修复为传 IDF 参数，不再失真）。

**已知局限**: RSS 实体提取标签过宽（Trump 默认打标）；RSS 日期截断 ("Fri, 10 Ju")；Qwen3 自由文本动作需规范为枚举。

详见 `references/event-aggregation-v4.2.1.md`。

## 🆕 Frozen Event Schema (V4.3 Phase 3 输出)

每个事件输出 21 字段的标准化 JSON：

```json
{
  "event_id": "EVT-20260710-006",
  "subject": {"name": "Apple", "type": "Company"},
  "action":  {"type": "SUES", "detail": "OpenAI over stealing trade secrets"},
  "object":  {"name": "OpenAI", "type": "Company"},
  "event_type": "Legal",
  "source": {"primary_source": "DW News", "authority": 16, "source_count": 8},
  "actors": [{"entity": "Apple", "type": "Company", "role": "Initiator"}],
  "confidence": 0.89, "coherence": 95.7,
  "stage": "active",
  "summary": "...", "keywords": [...], "related_entities": [...],
  "article_count": 8, "article_ids": [...],
  "extraction_method": "v4.3-saeo"
}
```

**confidence 公式**: `0.4 × source_authority + 0.3 × coherence + 0.2 × diversity + 0.1 × count_factor`

**stage 规则**: ≤2h→breaking, ≤24h→developing, ≤7d→active, ≤30d→stable, >30d→closed

这是 Phase 1 (信息→事件) 与 Phase 2 (事件→情报分析) 之间的"事实契约层"。

详见 `references/event-aggregation-v4.2.1.md`。

## 🆕 L9 洞察生成器 (`news_intel/generator.py`)

事件 → Insight。`generate_for_event()` 自动路由:
- Tier A 事件 → DeepSeek V4 Flash
- 其余 → Qwen3-1.7B 本地
- 不可用 → 降级跳过

⚠️ `.format()` 陷阱: prompt 中的 JSON 花括号必须双写 `{{` `}}` 转义。

详见 `references/event-aggregation-v4.md` 和 `references/event-aggregation-v4.1.md`。

## 🆕 V1 Schema 升级（Event-centric）

PostgreSQL 从 Article-center 升级为 Event-center，新增 11 张表（sources/entities/events/insights 及关联表）。迁移脚本: `api/migrate_v1.sql` + `api/migrate_data.py`。详见 `references/v1-schema-upgrade.md`。

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
