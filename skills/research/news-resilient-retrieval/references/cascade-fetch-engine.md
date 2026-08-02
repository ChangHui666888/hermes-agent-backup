# Cascade Full-Text Fetch Engine — 文章正文提取降级链路

> RSS 只提供标题+摘要。当需要文章全文时，使用 cascade 引擎逐级尝试。
> 对应 pipeline: `auto-pipeline.py Step 3 (batch.py) → core/fetchers.py`

## 架构（v2 — 重构后）

```
rss-scanner.py → rss-archive.db（摘要）
   ↓
auto-pipeline.py
  Step 0: Cleanup ← 清理空占位行 (fetch_strategy IS NULL + retry≥3)
  Step 1: Sync+Score ← news_intel.pipeline（评分）
  Step 2: RSS FullText ← 摘要≥200字直接入库（0成本）
  Step 3: Fetch (batch.py) ← cascade 降级链路（独立 try 块）
  Step 3.5: Recovery ← batch.py --force-strategy（独立 try 块，Step3失败不影响）
  Step 4: Aggregate ← SAO 事件聚类
  Step 5-6: Cloud Sync/Push
```

### 进程锁（防多实例并发）

`auto-pipeline.py` 内置时间戳式进程锁，避免 cron 重叠：

```python
# 锁文件: .pipeline.lock（在 SCRIPT_DIR 下）
def acquire_lock():
    # O_CREAT | O_EXCL → 原子创建
    # 锁已存在 → 检查 mtime 距今是否 < BATCH_TIMEOUT
    #   是 → [SKIP] 退出（已有实例在跑）
    #   否 → 清理旧锁，重试 acquire

# atexit 注册自动清理
import atexit
atexit.register(release_lock)
```

Windows 兼容性：`os.kill(pid, 0)` 在 Windows 上不支持 signal 0（对存活进程也报 WinError 87），改用 `os.path.getmtime()` + `BATCH_TIMEOUT` 判定。详见 `references/windows-compatibility.md`。

### Step 3 → Step 3.5 独立 try 块

v2 重构将 Step 3 和 Step 3.5 拆为两个独立 `try` 块：
- Step 3 (batch.py) 异常 → 不影响 Step 3.5 Recovery
- Step 3.5 现在也是调 `batch.py --force-strategy searxng_alt,tavily`，不再直接发 HTTP
- 临时文件使用 `tempfile.NamedTemporaryFile`，不再硬编码 `_fetch_tmp.jsonl`

### intel_id 不漏写

Step 3 的 SQL 查询现在直接取出 `ni.id`：

```sql
SELECT DISTINCT rr.article_url, ni.id FROM news_intelligence ni ...
--                                    ^^^^^^  直接带出 intel_id
```

存入 `url_to_intel` 字典，落库时直接引用，不再反查 SELECT + walrus 三元。

### Step 3.5 Recovery

```python
def _run_recovery_batch(candidates, strategy_order, timeout_s, label):
    # 1. 写 url\t标题 临时文件
    # 2. subprocess call batch.py --force-strategy searxng_alt,tavily
    # 3. 解析 JSONL → 写 DB
    # candidates: [(article_url, intel_id, title), ...]
```

## Cascade 策略列表（按优先级）

| 策略 | 依赖 | 适用场景 | timeout | cost |
|------|------|---------|---------|------|
| `direct` | httpx | 无/低反爬站点 | 15-30s | 1 |
| `archive` | httpx · web.archive.org | 403/404/被删文章 | 15s | 1 |
| `google_cache` | httpx · Google Cache | 被墙/临时不可用 | 15s | 1 |
| `scrapling` | scrapling (TLS指纹) | Cloudflare 防护 | 20-45s | 2 |
| `browser` | Playwright Chromium | DataDome/强反爬 (Bloomberg/WSJ/FT) | 30s | 3 |
| `jina` | curl -4 · r.jina.ai | 第三方免费API，自带反爬绕过(通用兜底) | 10s | 2 |
| `tavily` | curl -4 · api.tavily.com | AI搜索摘要(付费墙/反爬站的最后一层) | 10s | 3 |
| `search_snippet` | (外部注入) | 终极兜底，拿摘要总比空手强 | — | 1 |

每种策略成功后用 `trafilatura` / `readability` 提取正文（Markdown格式）。

## Domain Profiles 配置

`config/domain_profiles.py` 维护每个网站的反爬画像：

```python
# 强反爬/付费墙 → archive/jina/tavily 优先（browser 30s timeout不够）
"bloomberg.com": DomainProfile(
    strategy_order=["archive", "google_cache", "jina", "tavily", "search_snippet"],
    known_failing=["direct", "scrapling", "browser"],
)
"wsj.com": DomainProfile(
    strategy_order=["browser", "archive", "google_cache", "search_snippet"],
    known_failing=["scrapling"],
)

# 强反爬 + browser 被检测 → 非浏览器策略兜底
"reuters.com": DomainProfile(
    strategy_order=["archive", "google_cache", "jina", "tavily", "search_snippet"],
    known_failing=["scrapling", "browser"],
    # browser 被反检测 Target crashed → 依赖 archive/jina/tavily
)

# 强反爬 + browser 被检测 → jina/tavily 接管
"marketwatch.com": DomainProfile(
    strategy_order=["direct", "archive", "google_cache", "jina", "tavily", "search_snippet"],
    known_failing=["scrapling", "browser"],
)

# 中等反爬 → scrapling 可绕过
"cnbc.com": DomainProfile(
    strategy_order=["direct", "scrapling", "archive", "search_snippet"],
)

# 默认（未知域名）
DEFAULT_STRATEGY_ORDER = [
    "direct", "archive", "scrapling", "browser", "jina", "tavily", "search_snippet",
]
```

### 配置经验法则

1. 先测 `direct` — 大多数站点可用
2. 如 401/403 → 测 `browser`（Playwright，需 `playwright install chromium`）
3. 如 browser 也失败（Target crashed）→ 加入 `known_failing`
4. 加入 `jina` 和 `tavily` 作为非浏览器第三方兜底
5. 在 `notes` 字段写明实测结论

## 关键网络兼容性

### httpx 0.28 Windows 兼容性

**问题：** httpx 0.28+ 在 Windows + 代理环境下，`http2=True`（默认）导致间歇性 SSL 超时：

```
ConnectTimeout: _ssl.c:989: The handshake operation timed out
```

**修复：** `_make_client` 中禁用 http2 并设置激进超时：

```python
kwargs = {
    "headers": DEFAULT_HEADERS,
    "follow_redirects": True,
    "timeout": httpx.Timeout(connect=5, read=15, write=10, pool=5),
    "http2": False,
}
```

### 代理类型

| 类型 | httpx 兼容性 | 推荐 | 备注 |
|------|-------------|------|------|
| `socks5://127.0.0.1:10808` | ✅ 稳定 | ✅ 推荐 | rss-scanner.py 使用此方案 |
| `http://...` (CONNECT) | ⚠️ 间歇超时 | ❌ | httpx 0.28 + HTTP CONNECT 不稳定 |

### IPv6 问题 + curl -4 方案

`jina` 和 `tavily` 策略不能用 httpx（SNI 问题），改用 `curl -4` 子进程强制 IPv4：

```python
# Jina Reader: 免费 API，专注 LLM Markdown 提取
import subprocess
result = subprocess.run(
    ["curl", "-4", "-s", "--max-time", str(int(timeout)),
     f"https://r.jina.ai/{url}",
     "-H", "Accept: text/plain, text/markdown, */*"],
    capture_output=True, text=True, timeout=timeout+2)

# Tavily: AI搜索摘要
result = subprocess.run(
    ["curl", "-4", "-s", "--max-time", str(int(timeout)),
     "https://api.tavily.com/search",
     "-H", "Content-Type: application/json",
     "-d", json_payload],
    capture_output=True, text=True, timeout=timeout+2)
```

IPv6 根因：`r.jina.ai` 和 `api.tavily.com` 都解析出 IPv6 地址，但本机网络 IPv6 不通。

## Browser 策略调优

```python
# core/fetchers.py fetch_browser
timeout: float = 30.0  # 从 60s 降至 30s
UA: "Chrome/131.0.0.0"  # 从 124 升级
```

增强措施：
- **资源拦截**: 阻塞图片/字体/样式/媒体（提速 3-5x + 降低检测面）
- **WebGL 伪装**: 伪造 `Intel Inc. / Intel Iris OpenGL Engine`
- **hardwareConcurrency**: 固定 8（防 parallelism 检测）
- **滚动策略**: 半屏滚动（非全屏），更类人
- **内容选择器**: 扩展 `main`, `.story-body`, `.story-content`

## batch.py 参数

```python
# auto-pipeline.py Step 3（主抓取）
"--rate-delay", "0.3",          # RateLimiter 已有域名级锁
"--max-workers", "1",            # 保守单线程
"LIMIT 5"                        # SQL 中: 每批次 5 URL

# auto-pipeline.py Step 3.5（恢复抓取）
"--rate-delay", "0.3",
"--max-workers", "1",
"--force-strategy", "searxng_alt,tavily"  # 忽略域名profile，强制恢复策略
```

### 命令行新参数（batch.py）

| 参数 | 用途 | 示例 |
|------|------|------|
| `--force-strategy` | 逗号分隔，强制级联顺序，忽略域名profile | `--force-strategy searxng_alt,tavily` |
| `--title` | 配合 `--url` 单条模式传递标题 | `--url "https://..." --title "Article Title"` |
| URL文件格式 | `url\ttitle` tab分隔行，纯URL向后兼容 | `https://...\tGaza ceasefire` |

### 调优路径

```
1. 固定 max-workers=1, rate-delay=0.3（保守启动）
2. 5 URL 批次稳定 < 120s → 加 LIMIT 到 8
3. 每改一个参数，测 2 轮
4. 并发（max-workers=2）留到最后——Bloomberg/FT等硬站会阻塞整批
```

## Hermes Cron 管理

`no_agent` cron 任务必须在 `~/.hermes/scripts/` 目录下放脚本：

```bash
# 创建 wrapper（该目录下已存在 rss-scanner.py, news-pipeline.py 等）
cat ~/.hermes/scripts/auto-pipeline.py
# → 内容：Python subprocess 调用实际脚本路径

# 注册 cron 任务
hermes cron create "every 15m" \
  --script "auto-pipeline.py" \
  --no-agent \
  --deliver local \
  --name "auto-pipeline"

# 查看任务
hermes cron list
hermes cron list --all  # 包含已暂停的

# 管理
hermes cron pause <id>
hermes cron resume <id>
hermes cron run <id>     # 手动触发
hermes cron remove <id>
```

**注意：** 旧格式的 `profiles/<name>/cron/jobs.json` 已被新系统废弃，
所有任务通过 `hermes cron` CLI 管理，脚本放在 `~/.hermes/scripts/`。

## 诊断步骤

### 验证 Playwright
```bash
python -c "from playwright.sync_api import sync_playwright; print('OK')"
playwright install chromium  # 如失败
```

### 验证代理
```bash
curl -x socks5://127.0.0.1:10808 -s -o /dev/null -w "%{http_code}" --max-time 10 https://www.bbc.com
```

### 单 URL 全链路测试
```bash
echo "https://www.bloomberg.com/..." > _test.txt
python batch.py --urls _test.txt --out _test.jsonl --max-workers 1 --rate-delay 0.3 --verbose
# 检查 cost_trace 看每步策略结果
```

## 常见失败模式

| 症状 | 根因 | 处理 |
|------|------|------|
| SSL handshake 间歇超时 | httpx `http2=True` + Windows | `http2=False` |
| BBC/Reuters 等 https 全超时 | httpx + HTTP CONNECT proxy | 改用 SOCKS5 |
| 每批 50 URL 超时 600s | batch 太大 | `LIMIT 5` |
| 策略全失败: `none:0/49` | browser 不可用 + 其他被跳过 | 检查 Playwright + known_failing |
| Browser `Target crashed` | 反检测杀死 headless Chrome | 加入 known_failing，改用 jina/tavily |
| Tavily 恢复 0/3 | API key 过期 | 检查 `TAVILY_API_KEY` |
| jina `ConnectTimeout` | IPv6 不通或 httpx SNI | 改用 `curl -4`（已在代码中修复） |
| SearXNG 恢复 0/9 | SearXNG 未索引该页面 | 正常行为，不是 bug |
| Cloud Sync 10054 | nginx body 限制或防火墙 | 降低 CHUNK=20，加重试 |
| 高失败率(66%→44%→10%→2%) | 好抓的抓完，剩反爬源 | 正常衰减。archive/jina/tavily 兜底 |
| cron 任务不执行 | 脚本不在 `~/.hermes/scripts/` | 放 wrapper 到该目录 |
