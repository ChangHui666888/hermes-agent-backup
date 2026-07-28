# Cascade Full-Text Fetch Engine — 文章正文提取降级链路

> RSS 只提供标题+摘要。当需要文章全文时，使用 cascade 引擎逐级尝试。
> 对应 pipeline: `auto-pipeline.py Step 3 (batch.py) → core/fetchers.py`

## 架构

```
rss-scanner.py → rss-archive.db（摘要）
   ↓
auto-pipeline.py
  Step 1: Sync+Score ← news_intel.pipeline（评分）
  Step 2: RSS FullText ← 摘要≥200字直接入库（0成本）
  Step 3: Fetch (batch.py) ← cascade 降级链路 ↓
    3.5 Recovery ← SearXNG / Tavily 兜底
  Step 4: Aggregate ← SAO 事件聚类
  Step 5-6: Cloud Sync/Push
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
# 强反爬/付费墙 → browser 优先
"bloomberg.com": DomainProfile(
    strategy_order=["browser", "archive", "google_cache", "search_snippet"],
    known_failing=["direct", "scrapling"],
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
# auto-pipeline.py Step 3
"--rate-delay", "0.3",        # RateLimiter 已有域名级锁
"--max-workers", "1",          # 保守单线程
"LIMIT 5"                      # SQL 中: 每批次 5 URL
```

先跑 `LIMIT 5` 验证稳定性，确认后再逐步加到 10-20。

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
