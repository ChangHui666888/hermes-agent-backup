# Cascade Engine Production Optimization

> Production-level cascade engine (`core/fetchers.py`) for the news intelligence pipeline.
> Complement to the agent-level fallback strategy in the main SKILL.md.

## Architecture Boundary

```
auto-pipeline.py          ← 编排层：查DB → 调子进程 → 写DB → 记日志
  └── subprocess(batch.py) ← 调度层：CLI params → ThreadPoolExecutor → JSONL
       └── extract_single() ← 级联引擎 core/fetchers.py
            ├── fetch_direct()       httpx, SOCKS5 proxy
            ├── fetch_archive()      web.archive.org
            ├── fetch_google_cache() webcache.googleusercontent.com
            ├── fetch_scrapling()    TLS fingerprinting
            ├── fetch_browser()      Playwright (30s timeout, resource blocking)
            ├── fetch_jina_reader()  r.jina.ai via curl -4
            ├── fetch_tavily()       api.tavily.com via curl -4
            └── fetch_searxng_alt()  SearXNG → alternate source
```

**Golden rule**: auto-pipeline.py must NEVER contain HTTP requests to target sites.
Only `httpx.post` to `CLOUD_API` (own cloud service) is allowed in the orchestration layer.

## httpx 0.28 + Windows + Proxy: The SSL Hang

### Symptom
```log
ConnectTimeout: _ssl.c:989: The handshake operation timed out
```
Intermittent — same URL sometimes works, sometimes hangs.

### Root cause
httpx 0.28 defaults to `http2=True`. On Windows, HTTP CONNECT proxy (`http://127.0.0.1:10808`) combined with HTTP/2 causes intermittent SSL handshake failures in `httpcore`. The proxy (Clash/V2Ray) handles HTTP/2 CONNECT poorly on Windows.

### Fixes applied

**Primary fix**: `http2=False` in `_make_client()`
```python
kwargs = {"http2": False, ...}
```
This is the single most impactful change. Eliminated all SSL timeouts.

**Secondary fix**: SOCKS5 proxy instead of HTTP CONNECT
```python
proxy = "socks5://127.0.0.1:10808"
```
SOCKS5 is more compatible with httpx than HTTP CONNECT on this network.
Env var `SOCKS5_PROXY` overrides this. Do NOT fall back to `HTTPS_PROXY` — it's `http://127.0.0.1:10808` which causes the SSL issue.

**Tertiary fix**: Aggressive per-request timeouts
```python
timeout = httpx.Timeout(connect=5, read=15, write=10, pool=5)
```
Fast fail — don't wait 30s for a blocked connection.

### Verification
```bash
# Before: hangs
python -c "import httpx; httpx.Client(http2=True).get('https://www.bbc.com')"
# After: OK
python -c "import httpx; httpx.Client(http2=False).get('https://www.bbc.com')"
```

## Jina Reader: Overcoming IPv6 + SNI Issues

`r.jina.ai` resolves to both IPv4 (`154.83.14.134`) and IPv6 (`2a03:2880:...`).
IPv6 is unreachable from this network. httpx with raw IP + Host header has SNI issues.

### Fix: Use `curl -4` via subprocess
```python
subprocess.run(["curl", "-4", "-s", "--max-time", "10", reader_url], ...)
```
`curl -4` forces IPv4 and handles SNI correctly.
Timeout: 10s (fast fail if unreachable).

### Alternative: Tavily for search-based fallback
Same `curl -4` approach. Tavily returns AI-generated summaries (100-500 chars).
Key: `tvly-dev-*` — free dev key, works well.

## Process Lock: Prevent Concurrent Pipeline Instances

### Problem
Multiple `auto-pipeline.py` instances running simultaneously, overwriting each other's temp files and DB connections.

### Solution: File-based lock with PID validation
```python
LOCK_FILE = ".pipeline.lock"

def acquire_lock():
    # O_EXCL atomic create + PID write
    fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return True
    # On FileExistsError: check PID, clean up if dead, retry

atexit.register(release_lock)
```

**Windows caveat**: `atexit` doesn't fire when killed by `timeout` command or SIGKILL.
PID validation in `acquire_lock()` handles orphaned locks from dead processes.

## Strategy Effectiveness vs Content Quality

### DB Query Pattern
```sql
SELECT nc.fetch_strategy, COUNT(*),
       SUM(CASE WHEN length(nc.content_md) >= 2000 THEN 1 ELSE 0 END) as good
FROM news_content nc
GROUP BY nc.fetch_strategy;
```

### Measured effectiveness (from production DB)

| Strategy | Avg chars | Usefulness | Notes |
|----------|-----------|------------|-------|
| `direct` | 4,940 | 100% | Full article body |
| `searxng_alt` | 4,163 | 100% | Alternate source recovery |
| `archive` | 910 | 100% | Wayback Machine snapshots |
| `rss_fulltext` | 283 | 100% | Zero-cost RSS descriptions |
| `tavily` | 260 | 100% | AI search summary |
| `jina` | 265-753 | 100% | Third-party reader API |

## Domain Profile Patterns

### Hard targets (anti-bot / paywall)

```python
"reuters.com": strategy_order=["archive", "google_cache", "jina", "tavily"]
"marketwatch.com": strategy_order=["direct", "archive", "google_cache", "jina", "tavily"]
"bloomberg.com": strategy_order=["browser", "archive", "google_cache"]
```

**Bloomberg**: Playwright browser CAN bypass (DataDome detection evaded with resource blocking + WebGL spoofing).
**Reuters**: Playwright `Target crashed` — site detects headless browser aggressively. Browser strategy in `known_failing`.
**MarketWatch**: All local strategies fail. Only Jina/Tavily provide any content.

### Strategy removal pattern
When a strategy is proven to fail for a domain, add it to `known_failing`:
```python
known_failing=["scrapling", "browser"]  # Skip these entirely
```
This prevents wasting 30-60s per URL on strategies known to fail.

## BrowserPool: 半持久化 Playwright 实例

### 问题
`fetch_browser` 每次调用都 `sync_playwright()` → `chromium.launch()` → 抓取 → `browser.close()`。
单次 launch 开销 3-5 秒，连续抓数百篇时累计可观。

### 方案：进程级单例 BrowserPool
```python
class BrowserPool:
    _instance = None
    _browser = None
    _launch_count = 0  # 类变量，跨实例共享

    @classmethod
    def get_browser(cls):
        # 双重检查锁 + 崩溃检测 → 自动 relaunch
        ...
        return cls._instance._browser
```

`fetch_browser()` 改为从 pool 取 browser 实例，创建轻量 `context` 和 `page`，用完 `context.close()` 但不关闭 browser。进程退出时 `atexit.register(BrowserPool.close_all)` 清理。

### 崩溃恢复
`_ensure_browser()` 中每次获取前调用 `browser.is_connected()`，失败时自动 re-launch 并输出 `[browser_pool] browser crashed` 警告。无需外部监控。

### 限制
- `max-workers=1` 场景下 pool 仅服务单线程，主要节省重复 launch 开销
- `max-workers=N` 时多个 context 共享同一 browser 进程，需注意 `context` 并发安全

## cascade_timeout: 单 URL 级联总超时

### 问题
默认 cascade 会尝试完所有策略（最多 6-7 个）。当某些策略自身超时较长时，一个难抓的 URL 可拖 200s+。

### 方案：软截止
```python
def extract_single(url, ..., cascade_timeout=90.0):
    deadline = time.monotonic() + cascade_timeout
    for strategy in order:
        if time.monotonic() >= deadline:
            break  # 保留之前策略已获取的 partial content
        result = fn(url)
```

**软截止**：不中断正在执行的单个策略，仅在策略间检查。实际总耗时可能比 `cascade_timeout` 多出一个最长策略的自身超时（当前最大约 30s）。

### 配合 batch.py 的 future.timeout
batch.py 已有 `future.result(timeout=120)` 作为最后防线。cascade_timeout=90s 先于 120s 触发。

## CONTENT_PUSH: 全量→增量

### 问题
Step 6 每次推送全部 ~780 篇文章（16 chunks × 50 篇），云主机负载过高返回 502/10054/10061。

### 修复
```sql
WHERE nc.content_len > 0
  AND (nc.fetch_at > ? OR nc.created_at > ?)  -- 仅本轮新增
```
基于 pipeline 启动时间 `t0` 过滤，每 15 分钟 cron 周期通常新增 5-20 篇，1 个 chunk 完成。

## 架构原则：Single URL > Batch > Pipeline

### 分层依赖
```
URL  ← 唯一核心：extract_single()
 ↓
Batch ← 调度器：submit(extract_single) → collect
 ↓
Pipeline ← 编排：cron → sync → batch → aggregate → push
```

**约束**：
1. 所有抓取逻辑必须通过 `extract_single()` 调用。不允许裸 httpx/curl 在编排层出现。
2. Recovery 也是 cascade 策略——`searxng_alt`、`tavily` 注册在 `STRATEGY_FN` 中。
3. Pipeline 层只做编排，不包含任何 HTTP 请求（除自家云 API 外）。

### 验证
```bash
grep "WHERE nc.content_len" auto-pipeline.py | grep "fetch_at"
# 应输出含 `AND (nc.fetch_at > ? OR nc.created_at > ?)` 的行
```
## Clean Architecture: Recovery as Cascade Strategy

### Before (violation)
`auto-pipeline.py` Step 3.5 contained:
- Inline `httpx.get("http://searxng:8080/search")` — HTTP request in orchestration
- Inline `httpx.post("https://api.tavily.com/search")` — duplicated the already-broken httpx pattern
- `from core.fetchers import _extract_main_text` — extraction logic in orchestration
- Hardcoded Tavily API key — credential in wrong layer

### After (fixed)
1. `fetch_searxng_alt()` and `fetch_tavily(title=...)` in `core/fetchers.py`
2. `batch.py` gets `--force-strategy` and `url\ttitle` support
3. `auto-pipeline.py` Step 3.5: pure orchestration — query candidates → write temp file → subprocess(batch.py) → parse JSONL → write DB → log

### Verifying the boundary
```bash
# auto-pipeline.py should have ZERO httpx.get/post (except CLOUD_API)
grep -n "httpx\.\(get\|post\)" auto-pipeline.py | grep -v "CLOUD_API\|100.107.117.23"

# core/fetchers.py is WHERE all HTTP calls belong
grep -c "httpx\.\(get\|post\)\|curl -4" core/fetchers.py
```
