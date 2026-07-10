---
name: blogwatcher
description: "Monitor blogs and RSS/Atom feeds via blogwatcher-cli tool."
version: 2.0.0
author: JulienTant (fork of Hyaxia/blogwatcher)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [RSS, Blogs, Feed-Reader, Monitoring]
    homepage: https://github.com/JulienTant/blogwatcher-cli
prerequisites:
  commands: [blogwatcher-cli]
---

# Blogwatcher

Track blog and RSS/Atom feed updates with the `blogwatcher-cli` tool. Supports automatic feed discovery, HTML scraping fallback, OPML import, and read/unread article management.

## Installation

## Installation

Pick one method:

- **Go:** `go install github.com/JulienTant/blogwatcher-cli/cmd/blogwatcher-cli@latest`
- **Docker:** `docker run --rm -v blogwatcher-cli:/data ghcr.io/julientant/blogwatcher-cli`
- **Binary (Linux amd64):** `curl -sL https://github.com/JulienTant/blogwatcher-cli/releases/latest/download/blogwatcher-cli_linux_amd64.tar.gz | tar xz -C /usr/local/bin blogwatcher-cli`
- **Binary (Linux arm64):** `curl -sL https://github.com/JulienTant/blogwatcher-cli/releases/latest/download/blogwatcher-cli_linux_arm64.tar.gz | tar xz -C /usr/local/bin blogwatcher-cli`
- **Binary (macOS Apple Silicon):** `curl -sL https://github.com/JulienTant/blogwatcher-cli/releases/latest/download/blogwatcher-cli_darwin_arm64.tar.gz | tar xz -C /usr/local/bin blogwatcher-cli`
- **Binary (macOS Intel):** `curl -sL https://github.com/JulienTant/blogwatcher-cli/releases/latest/download/blogwatcher-cli_darwin_amd64.tar.gz | tar xz -C /usr/local/bin blogwatcher-cli`
- **Binary (Windows amd64):** 
  ```powershell
  # Download
  curl -L -o blogwatcher.zip "https://github.com/JulienTant/blogwatcher-cli/releases/download/v0.2.1/blogwatcher-cli_windows_amd64.zip"
  # Extract
  unzip blogwatcher.zip -d blogwatcher-install
  # Install (add to PATH)
  mkdir -p ~/bin
  cp blogwatcher-install/blogwatcher-cli.exe ~/bin/
  export PATH="$HOME/bin:$PATH"
  # Persist in bashrc
  echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
  ```
  
  **Windows proxy caveat:** If behind a firewall (e.g., GitHub is blocked), use `--socks5-hostname` with curl:
  ```bash
  curl -sL --socks5-hostname 127.0.0.1:10808 \
    "https://github.com/JulienTant/blogwatcher-cli/releases/download/v0.2.1/blogwatcher-cli_windows_amd64.zip" \
    -o blogwatcher.zip
  ```

All releases: https://github.com/JulienTant/blogwatcher-cli/releases

## Windows/PATH 持久化

将 `~/bin` 加入 shell 启动文件：
```bash
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```
## 与 Hermes Cron 集成

将 blogwatcher 配置为 Hermes cron job 可定期扫描 RSS：

```bash
# 1. 创建保活脚本
cat > ~/.hermes/scripts/rss-scan.sh << 'EOF'
#!/usr/bin/env bash
blogwatcher-cli.exe scan 2>&1
blogwatcher-cli.exe articles 2>&1 | head -20
EOF
chmod +x ~/.hermes/scripts/rss-scan.sh

# 2. 创建 cron job（每 2 小时扫描一次）
hermes cron create "every 2h" \
  --name "rss-scan" \
  --script "rss-scan.sh" \
  --no-agent
```

## Known Pitfalls

- **Go 二进制不支持 SOCKS5 代理** — `HTTP_PROXY=socks5://...` 会导致 `proxyconnect tcp: dial tcp 127.0.0.1:10808: loopback not authorized`。在需要代理时使用 `HTTP_PROXY=http://proxy:port` 而非 `socks5://`，或直接连接（RSS 服务通常无需代理）。
- **自动 Feed 发现可能失败** — 部分网站不提供 RSS/Atom autodiscovery meta tag。使用 `--feed-url` 明确指定 Feed 地址。
- **Windows 路径** — 在 git-bash 中，`blogwatcher-cli.exe` 需要位于 PATH 中。推荐 `~/bin/` 而非系统目录。
1. Download the Windows binary:
```bash
curl -sL --socks5-hostname 127.0.0.1:10808 \
  "https://github.com/JulienTant/blogwatcher-cli/releases/download/v0.2.1/blogwatcher-cli_windows_amd64.zip" \
  -o /tmp/blogwatcher.zip
```

2. Extract to `~/bin/` (add to PATH via `~/.bashrc`):
```bash
unzip -o /tmp/blogwatcher.zip -d /tmp/blogwatcher-install
mkdir -p ~/bin
cp /tmp/blogwatcher-install/blogwatcher-cli.exe ~/bin/
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
```

3. Verify:
```bash
export PATH="$HOME/bin:$PATH"
blogwatcher-cli.exe --version
```

### All Platforms

All releases: https://github.com/JulienTant/blogwatcher-cli/releases

### Docker with persistent storage

By default the database lives at `~/.blogwatcher-cli/blogwatcher-cli.db`. In Docker this is lost on container restart. Use `BLOGWATCHER_DB` or a volume mount to persist it:

```bash
# Named volume (simplest)
docker run --rm -v blogwatcher-cli:/data -e BLOGWATCHER_DB=/data/blogwatcher-cli.db ghcr.io/julientant/blogwatcher-cli scan

# Host bind mount
docker run --rm -v /path/on/host:/data -e BLOGWATCHER_DB=/data/blogwatcher-cli.db ghcr.io/julientant/blogwatcher-cli scan
```

### Migrating from the original blogwatcher

If upgrading from `Hyaxia/blogwatcher`, move your database:

```bash
mv ~/.blogwatcher/blogwatcher.db ~/.blogwatcher-cli/blogwatcher-cli.db
```

The binary name changed from `blogwatcher` to `blogwatcher-cli`.

## Common Commands

### Managing blogs

- Add a blog: `blogwatcher-cli add "My Blog" https://example.com/rss.xml`
- Add with explicit feed (same as above): `blogwatcher-cli add "My Blog" https://example.com/feed.xml`
- Add with HTML scraping: `blogwatcher-cli add "My Blog" https://example.com --scrape-selector "article h2 a"`
- List tracked blogs: `blogwatcher-cli blogs`
- Remove a blog: `blogwatcher-cli remove "My Blog" --yes`
- Import from OPML: `blogwatcher-cli import subscriptions.opml`

> **注意:** `add` 命令的语法是 `add "name" "url"`，不是 `add "name" --feed-url "url"`。

### Scanning and reading

- Scan all blogs: `blogwatcher-cli scan`
- Scan one blog: `blogwatcher-cli scan "My Blog"`
- List unread articles: `blogwatcher-cli articles`
- List all articles: `blogwatcher-cli articles --all`
- Filter by blog: `blogwatcher-cli articles --blog "My Blog"`
- Filter by category: `blogwatcher-cli articles --category "Engineering"`
- Mark article read: `blogwatcher-cli read 1`
- Mark article unread: `blogwatcher-cli unread 1`
- Mark all read: `blogwatcher-cli read-all`
- Mark all read for a blog: `blogwatcher-cli read-all --blog "My Blog" --yes`

## Environment Variables

All flags can be set via environment variables with the `BLOGWATCHER_` prefix:

| Variable | Description |
|---|---|
| `BLOGWATCHER_DB` | Path to SQLite database file |
| `BLOGWATCHER_WORKERS` | Number of concurrent scan workers (default: 8) |
| `BLOGWATCHER_SILENT` | Only output "scan done" when scanning |
| `BLOGWATCHER_YES` | Skip confirmation prompts |
| `BLOGWATCHER_CATEGORY` | Default filter for articles by category |

## Example Output

```
$ blogwatcher-cli blogs
Tracked blogs (1):

  xkcd
    URL: https://xkcd.com
    Feed: https://xkcd.com/atom.xml
    Last scanned: 2026-04-03 10:30
```

```
$ blogwatcher-cli scan
Scanning 1 blog(s)...

  xkcd
    Source: RSS | Found: 4 | New: 4

Found 4 new article(s) total!
```

```
$ blogwatcher-cli articles
Unread articles (2):

  [1] [new] Barrel - Part 13
       Blog: xkcd
       URL: https://xkcd.com/3095/
       Published: 2026-04-02
       Categories: Comics, Science

  [2] [new] Volcano Fact
       Blog: xkcd
       URL: https://xkcd.com/3094/
       Published: 2026-04-01
       Categories: Comics
```

## Known Limitation: SOCKS5 Proxy Incompatibility

**blogwatcher-cli is a Go binary.** Go's `net/http` package supports `HTTP_PROXY` for HTTP CONNECT proxies only — it does **not** support SOCKS5 protocol. On systems where RSS feeds are only accessible via a SOCKS5 proxy (e.g., behind China's firewall):

```bash
# ❌ This will NOT work — Go cannot use SOCKS5
export HTTP_PROXY=socks5://127.0.0.1:10808
blogwatcher-cli scan
```

Error: `proxyconnect tcp: dial tcp 127.0.0.1:10808: address is loopback`

### Workaround: Python RSS Scanner

Use `scripts/rss-scanner.py` — a Python-based scanner that supports SOCKS5 via `pysocks`:

```bash
# Install dependency
uv pip install pysocks

# Run scanner
python ~/.hermes/scripts/rss-scanner.py
```

The Python scanner:
- Uses `socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 10808)` to patch all socket connections
- Can access BBC, Reuters, Bloomberg, Hacker News and other blocked feeds
- Supports concurrent fetching (default: 8 workers)
- Outputs structured JSON report

### Hybrid Strategy

| Component | When to Use | Proxy Support |
|-----------|-------------|---------------|
| `blogwatcher-cli` | Feeds directly accessible (TechCrunch, GitHub, arXiv) | ❌ No SOCKS5 |
| `scripts/rss-scanner.py` | Feeds behind firewall (BBC, Reuters, HN) | ✅ SOCKS5 via pysocks |
| Hermes Cron | Scheduled scanning (every 30m via `rss-scan` job) | ✅ Python script |

### Hermes Cron Integration

The RSS scanner can be run as a Hermes cron job:

```bash
hermes cron create "every 30m" \
  --name "rss-scan" \
  --script "rss-scan.sh" \
  --no-agent
```

Requires `scripts/rss-scan.sh` (wrapper that calls `scripts/rss-scanner.py`).

## Notes

- Auto-discovers RSS/Atom feeds from blog homepages when no `--feed-url` is provided.
- Falls back to HTML scraping if RSS fails and `--scrape-selector` is configured.
- Categories from RSS/Atom feeds are stored and can be used to filter articles.
- Import blogs in bulk from OPML files exported by Feedly, Inoreader, NewsBlur, etc.
- Database stored at `~/.blogwatcher-cli/blogwatcher-cli.db` by default (override with `--db` or `BLOGWATCHER_DB`).
- Use `blogwatcher-cli <command> --help` to discover all flags and options.

- Auto-discovers RSS/Atom feeds from blog homepages when no `--feed-url` is provided.
- Falls back to HTML scraping if RSS fails and `--scrape-selector` is configured.
- Categories from RSS/Atom feeds are stored and can be used to filter articles.
- Import blogs in bulk from OPML files exported by Feedly, Inoreader, NewsBlur, etc.
- Database stored at `~/.blogwatcher-cli/blogwatcher-cli.db` by default (override with `--db` or `BLOGWATCHER_DB`).
- Use `blogwatcher-cli <command> --help` to discover all flags and options.

---

## ⚠️ Known Limitation: Go binary cannot use SOCKS5 proxy

The `blogwatcher-cli` Go binary does **NOT** support SOCKS5 proxy via `HTTP_PROXY`/`HTTPS_PROXY` env vars (Go's stdlib HTTP client only supports HTTP CONNECT proxies, not SOCKS5). 

In environments where international RSS feeds are blocked (e.g., China firewall), use the **Python RSS Scanner** instead (see below).

---

## Python RSS Scanner (SOCKS5 Proxy Compatible)

When the Go binary cannot reach feeds through the firewall, use the Python-based scanner that supports SOCKS5 proxy routing.

### Architecture

```
Python Scanner (每30min via Hermes cron)
    │
    ├── 国际源 (BBC/Reuters/WSJ/arXiv...)
    │   └── SOCKS5 → 127.0.0.1:10808
    │
    └── 国内源 (人民网/新华网/央视...)
        └── 直连（不走代理）
```

### Setup

```bash
# Prerequisites
uv pip install pysocks

# Scanner script at:
~/.hermes/scripts/rss-scanner.py
~/.hermes/scripts/rss-scan.sh    # cron wrapper

# Create cron job
hermes cron create "every 30m" --name "rss-scan" --script "rss-scan.sh" --no-agent
```

### Storage

| 存储 | 位置 | 内容 |
|:----|:-----|:-----|
| SQLite 归档 | `~/.hermes/rss-archive.db` | 全量文章（date/category/source/title/summary/link） |
| Wiki 日报 | `wiki/RSS-Digest/{date}.md` | 按分类整理的每日摘要 |
| 去重状态 | `~/.hermes/rss-scanner-state.json` | 已推送文章的 URL 索引 |

### Database Schema

```sql
CREATE TABLE rss_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    category TEXT,       -- 通讯社/国家媒体/金融媒体/科技媒体/...
    source TEXT NOT NULL, -- 来源名（如 "Bloomberg Markets"）
    title TEXT,
    summary TEXT,
    link TEXT UNIQUE,     -- URL 去重
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX idx_date ON rss_articles(date);
CREATE INDEX idx_source ON rss_articles(source);
CREATE INDEX idx_category ON rss_articles(category);
```

### Category Mapping

```python
def categorize_feed(name):
    if "Reuters" in name or "Bloomberg" in name: return "通讯社"
    if "BBC" in name or "CNN" in name: return "国家媒体"
    if "FT " in name or "WSJ" in name: return "金融媒体"
    if "TechCrunch" in name or "The Verge" in name: return "科技媒体"
    if "Guardian" in name or "Al Jazeera" in name: return "地缘媒体"
    if "White House" in name or "Fed Press" in name: return "政府机构"
    if "arXiv" in name or "OpenAI" in name: return "科研/开源"
    if "Hacker News" in name or "Reddit" in name: return "实时信号"
    if "人民网" in name or "新华社" in name: return "中文央媒"
    return "其他"
```

### X/Nitter — 关键人物监控

通过 Nitter 匿名 RSS（无需 X 账号），支持监控：
- Trump (@realDonaldTrump)
- Elon Musk (@elonmusk)
- Bill Gates (@BillGates)
- 普京 / Kremlin (@KremlinRussia_E)
- Kevin Warsh (@KevinWarsh) — 美联储主席

注意：Nitter 实例普遍启用 Cloudflare 保护，Python 直接请求可能被拦截。需寻找未启用 Cloudflare 的实例。

### Query Examples

```bash
# 查某天的所有文章
sqlite3 ~/.hermes/rss-archive.db \
  "SELECT source, title FROM rss_articles WHERE date='2026-06-29'"

# 搜索关键词
sqlite3 ~/.hermes/rss-archive.db \
  "SELECT date, source, title FROM rss_articles
   WHERE title LIKE '%Trump%' OR summary LIKE '%Trump%'
   ORDER BY date DESC LIMIT 20"

# 统计每个来源的文章数
sqlite3 ~/.hermes/rss-archive.db \
  "SELECT source, count(*) FROM rss_articles GROUP BY source ORDER BY count(*) DESC"
```

### ⚠️ SOCKS5 Proxy Limitation

`blogwatcher-cli` is a Go binary — Go's `HTTP_PROXY` env var only supports HTTP CONNECT proxies, **not** SOCKS5. If your network requires SOCKS5 (e.g. behind the Great Firewall), blogwatcher will fail to reach blocked feeds.

**Symptoms:** `dial tcp <ip>:443: connectex: No connection could be made` or `request filter round trip failed`

**Workaround:** Use a Python-based RSS scanner that can use `pysocks` for SOCKS5 support:

```python
import socks, socket
socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 10808)
socket.socket = socks.socksocket
# Now urllib.request.urlopen() routes through SOCKS5
```

For a full production scanner with SQLite archiving + Wiki daily digest, see `media-intelligence-search` skill (RSS monitoring section).
