---
name: hermes-windows-deployment
description: "Deploy Hermes Agent as a persistent service on Windows: boot startup, gateway backgrounding, dashboard keep-alive via cron, RSS monitoring pipeline with SQLite+Wiki storage, and process lifecycle for git-bash environments."
version: 2.0.0
author: Agent
platforms: [windows]
trigger: user asks to set up Hermes to auto-start on Windows, create startup/boot scripts, run Gateway/Dashboard persistently, set up cron-based keep-alive, or deploy the RSS monitoring system with SOCKS5 proxy, SQLite archive, and Wiki daily digest.
---

# Hermes Windows Deployment

Run Hermes persistently on Windows without systemd: boot startup, background gateway, cron-based dashboard keep-alive, and the full RSS monitoring pipeline with SOCKS5 proxy routing, SQLite archival, and Wiki daily digest.

---

## Architecture

```
┌─ Windows Login ───────────────────────────────────────────────────┐
│                                                                    │
│  Startup\hermes-start.vbs (silent VBS launcher)                    │
│      ↓                                                             │
│  C:\Users\<user>\hermes-start.cmd                                 │
│      ├── hermes gateway run  (background → cron engine)           │
│      ├── hermes dashboard   (background → port 9119)              │
│      └── [RSS scanner starts on next cron tick]                   │
│                                                                    │
│  Cron Jobs:                                                        │
│    ├── hermes-dashboard  (every 5m, no-agent)  → keepalive       │
│    └── rss-scan          (every 30m, no-agent)  → 98 feeds scan   │
│                                                                    │
│  RSS Scanner Output:                                               │
│    ├── SQLite:  ~/.hermes/rss-archive.db                          │
│    │   └── table rss_articles (date, category, source, title,     │
│    │                            summary, link)                     │
│    └── Wiki:    ~/wiki/RSS-Digest/{YYYY-MM-DD}.md                 │
│        └── Daily digest grouped by category                        │
└────────────────────────────────────────────────────────────────────┘
```

---

## 1. Boot Startup

### 1a. Create Startup Script

`C:\Users\<user>\hermes-start.cmd`:

```batch
@echo off
cd /d C:\Users\<user>
set LOG_DIR=C:\Users\<user>\.hermes\logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Start Gateway (needed for cron scheduler)
start /B "" "C:\Program Files\Git\usr\bin\bash.exe" -c ^
  "cd /c/Users/<user> && nohup hermes gateway run > /c/Users/<user>/.hermes/logs/gateway.log 2>&1 &"

timeout /t 8 /nobreak > nul

REM Start Dashboard / Web UI
start /B "" "C:\Program Files\Git\usr\bin\bash.exe" -c ^
  "cd /c/Users/<user> && nohup hermes dashboard --skip-build --port 9119 --host 127.0.0.1 > /c/Users/<user>/.hermes/logs/dashboard.log 2>&1 &"
```

Key options:
- `--skip-build`: Essential for non-interactive contexts (no npm available).
- `--host 127.0.0.1`: Local-only binding. Use `--insecure` for network access (⚠ exposes API keys).
- Gateway **must** be running for cron jobs to fire.

### 1b. Create Silent VBS Launcher

`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\hermes-start.vbs`:
```vbs
CreateObject("WScript.Shell").Run "C:\Users\<user>\hermes-start.cmd", 0, False
```

The `0` flag hides the cmd window. On git-bash:
```bash
echo 'CreateObject("WScript.Shell").Run "C:\Users\<user>\hermes-start.cmd", 0, False' \
  > "$APPDATA/Microsoft/Windows/Start Menu/Programs/Startup/hermes-start.vbs"
```

---

## 2. Dashboard Keep-Alive

### 2a. Keep-Alive Script

`~/.hermes/scripts/hermes-dashboard-keepalive.sh`:
```bash
#!/usr/bin/env bash
DASHBOARD_PID=$(pgrep -f "hermes dashboard --skip-build" || true)
if [ -z "$DASHBOARD_PID" ]; then
  nohup hermes dashboard --skip-build --port 9119 --host 127.0.0.1 \
    > "$HOME/.hermes/logs/dashboard.log" 2>&1 &
  echo "[$(date)] Dashboard restarted"
else
  echo "[$(date)] Dashboard running (PID: $DASHBOARD_PID)"
fi
```

### 2b. Create Cron Job

```bash
hermes cron create "every 5m" \
  --name "hermes-dashboard" \
  --script "hermes-dashboard-keepalive.sh" \
  --no-agent
```

---

## 3. RSS Monitoring Pipeline (98 Feeds)

### 3a. Overview

The RSS system has three components:

```
Component           Language  Proxy    Storage           Frequency
──────────────────  ────────  ───────  ────────────────  ─────────
blogwatcher-cli     Go        No       SQLite (own DB)   (manual)
Python Scanner      Python    SOCKS5   SQLite + Wiki     every 30m (cron)
read_article SQL    SQL       N/A      rss-archive.db    (on demand)
```

- **blogwatcher-cli**: 71 feeds registered for CLI management, but Go binary cannot use SOCKS5 proxy. Used for feed list management only.
- **Python RSS Scanner**: The actual scanner that fetches all 98 feeds via SOCKS5 (international) or direct (domestic), deduplicates, and writes to SQLite + Wiki.
- **SQLite DB**: Full archive, searchable via `sqlite3`.
- **Wiki**: Daily digest by category, browsable in Obsidian.

### 3b. Proxy Routing (Critical for China Users)

Domestic websites (中国) MUST NOT use the proxy. International (blocked) sites MUST use SOCKS5.

```python
DOMESTIC_DOMAINS = [
    "stats.gov.cn", "people.com.cn", "xinhuanet.com", "cctv.com",
    "chinadaily.com.cn", "chinanews.com", "huanqiu.com", "ce.cn",
    "gov.cn", "pbc.gov.cn", "eastmoney.com",
    "36kr.com", "huxiu.com", "cls.cn", "xueqiu.com",
]

def needs_proxy(url):
    """International → SOCKS5. Domestic → direct."""
    from urllib.parse import urlparse
    domain = urlparse(url).hostname or ""
    for d in DOMESTIC_DOMAINS:
        if domain.endswith(d):
            return False
    return True
```

**In the scanner**: Per-feed proxy routing, not global socket patch. Domestic feeds use direct `urllib.request.urlopen()`. International feeds use `socket.socksocket` via `pysocks`.

### 3c. Source Matrix (74 International + 18 Nitter + 6 Domestic = 98)

Reference file: `references/rss-source-matrix.md` contains the full 98-source list organized by tier and category.

#### Tier Structure

| Tier | Count | Examples | Paywall |
|:-----|:------|:---------|:--------|
| **S** (事实源) | 23 | Reuters, AP, Bloomberg, WSJ, FT, arXiv, White House, Fed, SEC | 付费/免费 |
| **A** (传播层) | 39 | BBC, CNN, NYT, Guardian, TechCrunch, The Verge | 免费为主 |
| **B** (实时信号) | 10 | Hacker News, Reddit, Yahoo Finance | 免费 |
| **Nitter/X** | 18 | Trump, Musk, Gates, Kremlin, Kevin Warsh | 免费 (需匿名访问) |
| **中文央媒** | 6 | 人民网, 新华网, 央视, 中国新闻网, 中国日报, 环球网 | 免费 (直连) |

#### Category Distribution

```
通讯社     9 源   │  国家媒体   17 源   │  金融媒体   11 源
科技媒体   12 源  │  地缘媒体    5 源   │  政府机构   11 源
科研/开源   6 源  │  X/Nitter   18 源   │  中文央媒    6 源
实时信号    3 源  │  ───────────────────
                  │  总计       98 源
```

### 3d. Python Scanner Script

Located at `~/.hermes/scripts/rss-scanner.py` (also copied to profile scripts dir).

Key features:
- Concurrent fetching via `ThreadPoolExecutor(max_workers=8)`
- Per-feed proxy routing (SOCKS5 for international, direct for domestic)
- Dedup via in-memory state file + SQLite UNIQUE(link)
- Category auto-classification via `categorize_feed()` function
- Dual output: SQLite archive + Wiki daily digest

### 3e. SQLite Schema

```sql
CREATE TABLE rss_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    category TEXT,
    source TEXT NOT NULL,
    title TEXT,
    summary TEXT,
    link TEXT UNIQUE,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX idx_date ON rss_articles(date);
CREATE INDEX idx_source ON rss_articles(source);
CREATE INDEX idx_category ON rss_articles(category);
```

Query examples:
```bash
# Today's articles by source
sqlite3 ~/.hermes/rss-archive.db \
  "SELECT source, count(*) FROM rss_articles WHERE date='2026-06-29' GROUP BY source"

# Search for keyword
sqlite3 ~/.hermes/rss-archive.db \
  "SELECT date, source, title FROM rss_articles WHERE title LIKE '%Trump%' LIMIT 20"
```

### 3f. Wiki Daily Digest

Output path: `~/wiki/RSS-Digest/{YYYY-MM-DD}.md`

Format:
```markdown
# RSS 日报 — 2026-06-29

> 来源: 243 篇文章 | 10 个分类

## 通讯社 (5 篇)
- **[Reuters World]** Title...
  Summary text...
  _2026-06-29_ | [链接](url)

## 金融媒体 (12 篇)
...
```

### 3g. Nitter/X for Key Figures (No Login Needed)

Nitter is an anonymous X frontend that provides RSS without login. Use working instances:

```
https://nitter.freedit.eu/<username>/rss    ⚠️ May have Cloudflare
https://nitter.kavin.rocks/<username>/rss   ⚠️ May have Cloudflare
```

Currently monitored (18 accounts):
Trump, Biden/POTUS, Elon Musk, Bill Gates, Kremlin Russia, UK PM, EU Commission, ECB, Fed Chair, SEC, Treasury, IMF, World Bank, Kevin Warsh, Reuters, BBC Breaking, NASA, White House

**Known limitation**: Nitter instances frequently deploy Cloudflare protection. Python-based fetchers cannot pass Cloudflare JS challenges. If Nitter is blocked, fall back to:
- Traditional RSS media feeds (which carry the same news)
- RSSHub (same Cloudflare issue)
- Manual browser check via `browser_navigate`

---

## 4. Cron Job Management

### Current Jobs

| Name | Schedule | Script | Mode |
|:-----|:---------|:-------|:-----|
| `hermes-dashboard` | every 5m | `hermes-dashboard-keepalive.sh` | no-agent |
| `rss-scan` | every 30m | `rss-scan.sh` | no-agent |

### ⚠️ Profile Scripts Path (Critical)

The `--script` parameter for `hermes cron create` reads from the **profile's scripts directory**, NOT `~/.hermes/scripts/`.

| Component | Path |
|:----------|:-----|
| Where `--script` looks | `%LOCALAPPDATA%\hermes\profiles\<profile>\scripts\` |
| Where `~/.hermes/scripts/` resolves | `%LOCALAPPDATA%\hermes\profiles\<profile>\home\.hermes\scripts\` |
| **Fix** | Always copy scripts to BOTH locations |

```bash
# When creating cron scripts, always copy to profile scripts dir:
cp ~/.hermes/scripts/<script> "$(dirname $(hermes config path))/scripts/"
```

### Gateway Requirement
Cron jobs only fire when the Gateway is running (`hermes gateway run` or `hermes gateway install`). The startup script handles this, but for testing:
```bash
# Start gateway in background
terminal(command="hermes gateway run", background=true)

# Verify
hermes gateway status
```

---

## 5. Process Management

| Action | Command |
|--------|---------|
| Check dashboard status | `hermes dashboard --status` |
| Stop all dashboards | `hermes dashboard --stop` |
| Find PID | `pgrep -f "hermes dashboard"` |
| Kill by PID | `kill <PID>` |
| Check Gateway status | `hermes gateway status` |
| Check cron status | `hermes cron status` / `hermes cron list` |
| View logs | `tail -f ~/.hermes/logs/gateway.log` |
| View RSS report | `cat ~/.hermes/rss-scanner-report.json \| python -m json.tool` |
| Query SQLite | `sqlite3 ~/.hermes/rss-archive.db "SELECT ..."` |
| List cron jobs | `hermes cron list` |

---

## 6. Pitfalls

- **`start /B` path to bash.exe**: Must match actual Git for Windows install path (`C:\Program Files\Git\usr\bin\bash.exe`). Verify with `which bash`.
- **`python3` vs `python` on Windows**: The Microsoft Store `python3` stub returns exit code 49. Always use `python` (Hermes venv) in keep-alive scripts.
- **`--skip-build` required for headless**: Dashboard needs Node.js/npm for first build. Without `--skip-build`, startup hangs.
- **Startup folder timing**: VBS runs at login, before git-bash fully initializes. Using full bash.exe path bypasses this.
- **Cron needs Gateway**: Jobs only fire when `hermes gateway run` is active. Startup script must start Gateway first.
- **Dashboard ≡ Web UI:** `hermes dashboard` IS the web UI. There is no separate `hermes web-ui` command.
- **RSS scanner cron job path:** Cron scripts are resolved relative to `%LOCALAPPDATA%\\hermes\\profiles\\<name>\\scripts\\`, NOT `~/.hermes/scripts/`. Always copy scripts to both locations or use the profile scripts directory.
- **Nitter Cloudflare**: Nitter instances frequently deploy Cloudflare. Python RSS scanner cannot pass JS challenges. Fall back to traditional RSS.
- **SOCKS5 + Go incompatibility**: Go's `HTTP_PROXY` does not support SOCKS5. Use Python scanner for proxy-routed feeds. blogwatcher-cli (Go) is for feed list management only.
- **Profile scripts path**: Cron `--script` reads from `profiles/<name>/scripts/`, NOT `~/.hermes/scripts/`. Always copy scripts to both locations.
- **UAC blocks gateway install**: `hermes gateway install` needs admin rights for Windows Scheduled Task. If UAC prompt can't be answered, use `hermes-start.cmd` + VBS as the boot startup method instead.

## 7. Cron Engineering Template

所有 cron job 遵循统一模板。

### 7a. 文件结构

```
~/.hermes/scripts/          ← --workdir 指向这里（最稳定）
├── rss-scanner.py           ← 业务脚本
├── news-pipeline.py         ← wrapper: argparse + logging + run_xxx()
├── git-backup.sh            ← 简单启动器
└── logs/
    └── news-pipeline.log
```

### 7b. Shell 启动器

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python "$SCRIPT_DIR/xxx.py" "$@"
```

### 7c. Python Wrapper 模板

```python
import argparse, logging, os, sys, traceback
os.environ["PYTHONUNBUFFERED"] = "1"
LOG_FILE = os.path.join(os.path.dirname(__file__), "logs", "xxx.log")
logging.basicConfig(level=logging.INFO, handlers=[
    logging.FileHandler(LOG_FILE, encoding="utf-8"),
    logging.StreamHandler(sys.stdout)
])
# exit codes: 0=OK, 1=Pipeline, 2=Import
```

### 7d. 业务模块返回 Report dict → 写 JSON

```python
report = {"batch_input": N, "batch_new": N, "total_articles": N, "duration_sec": 1.0}
with open(os.path.expanduser("~/.hermes/xxx-report.json"), "w") as f:
    json.dump(report, f)
```

### 7e. ⚠️ `"30m"` vs `"every 30m"` 陷阱

```powershell
# ❌ 只执行一次！
hermes cron create "30m"  → Schedule: once in 30m, Repeat: 0/1

# ✅ 循环执行
hermes cron add "every 30m" → Schedule: every 30m, Repeat: ∞
```

### 7f. 创建命令（推荐形式）

```powershell
hermes cron add "every 30m" --name xxx --script xxx.py --workdir "C:\Users\<user>\AppData\Local\hermes\scripts" --no-agent
```
