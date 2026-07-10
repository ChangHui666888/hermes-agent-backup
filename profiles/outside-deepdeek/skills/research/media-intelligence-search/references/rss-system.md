# RSS Scanner 系统 — 已部署运行状态

> 本文件记录实际运行的 RSS 扫描系统配置。系统通过 Hermes cron job 每 5 分钟调度一次 `rss-scanner.py`，覆盖 98 个订阅源。

---

## 一、Cron 调度

| 字段 | 值 |
|------|-----|
| 任务名 | `rss-scan` |
| 调度频率 | `interval(5分钟)` — 每 5 分钟 |
| 运行模式 | `no_agent=true`（纯 Python 脚本，不调 LLM） |
| 累计运行 | 202+ 次 |
| 状态 | `enabled` |
| 所在文件 | `C:/Users/ChangHui/AppData/Local/hermes/cron/jobs.json` |

---

## 二、文件存储位置

| 用途 | 路径 |
|------|------|
| 扫描脚本 | `C:/Users/ChangHui/AppData/Local/hermes/scripts/rss-scanner.py` |
| 去重状态 | `~/.hermes/rss-scanner-state.json` |
| 扫描报告 | `~/.hermes/rss-scanner-report.json` |
| SQLite 存档 | `~/.hermes/rss-archive.db` |
| Wiki 日报 | `~/wiki/RSS-Digest/{YYYY-MM-DD}.md` |

---

## 三、SQLite 表结构

```sql
CREATE TABLE IF NOT EXISTS rss_articles (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    date       TEXT,         -- RSS pubDate, 前25字符
    category   TEXT,         -- 10个分类之一（见下）
    source     TEXT NOT NULL,-- 源名称（如 "Bloomberg Markets"）
    title      TEXT,         -- 文章标题
    summary    TEXT,         -- description 前300字符
    link       TEXT UNIQUE,  -- 文章 URL（去重键）
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX idx_date     ON rss_articles(date);
CREATE INDEX idx_source   ON rss_articles(source);
CREATE INDEX idx_category ON rss_articles(category);
```

---

## 四、字段定义

| 字段 | RSS 2.0 来源 | Atom 来源 | 长度限制 | 说明 |
|------|-------------|-----------|---------|------|
| `title` | `<item><title>` | `<entry><title>` | 全文 | unescape HTML |
| `url` | `<item><link>` | `<entry><link href>` | — | — |
| `date` | `<item><pubDate>` | `<entry><published>` / `<updated>` | 25字符 | 原始文本 |
| `summary` | `<item><description>` | `<entry><summary>` | 200字符 | unescape HTML |
| `category` | 由 `categorize_feed(name)` 根据源名关键字映射 | — | — | 10 个分类 |
| `source` | 配置中硬编码的显示名称 | — | — | — |

### 10 个分类映射规则

```
通讯社    ← Reuters / AP / Bloomberg / AFP
国家媒体  ← BBC / CNN / NBC / CBS / ABC / NYT / NPR / Politico / The Hill / Newsweek / Sky News / France 24 / WaPo
金融媒体  ← FT / WSJ / Economist / CNBC / MarketWatch / Barrons / Seeking Alpha / Investing / Yahoo Finance
科技媒体  ← TechCrunch / The Verge / Wired / Ars Technica / MIT / Engadget / VentureBeat / Space / Electrek / CleanTechnica / IEEE
地缘媒体  ← Guardian / DW / Le Monde / Al Jazeera / SCMP
政府机构  ← White House / Fed Press / ECB / SEC / UN News / NASA / UK Gov / BoE / IMF / World Bank / OECD
科研/开源 ← arXiv / OpenAI / Google AI / GitHub
实时信号  ← Hacker News / Reddit
X/Nitter  ← 含 "Nitter:" 前缀
中文央媒  ← 人民网 / 中国新闻网 / 中国日报 / 环球网 / 新华网 / 央视
```

---

## 五、98 个订阅源完整统计

| 大类 | 数量 | 路由 | 说明 |
|------|:----:|:----:|------|
| 通讯社 | 6 | SOCKS5 | Reuters×3, AP×2, Bloomberg |
| 国家媒体 | 17 | SOCKS5 | BBC×3, CNN×2, NBC, CBS, ABC, NYT, NPR, Politico, The Hill, Newsweek, Sky News, France 24, WaPo×2 |
| 金融媒体 | 11 | SOCKS5 | FT×2, WSJ×2, Economist, CNBC, MarketWatch, Barrons, Seeking Alpha, Investing, Yahoo Finance |
| 科技媒体 | 12 | SOCKS5 | TechCrunch, The Verge, Wired, Ars Technica, MIT Tech Review, Engadget, VentureBeat, Space.com, SpaceNews, Electrek, CleanTechnica, IEEE Spectrum |
| 地缘媒体 | 5 | SOCKS5 | Guardian, DW, Le Monde EN, Al Jazeera, SCMP |
| 政府机构 | 11 | SOCKS5 | White House, Fed, ECB, SEC, UN, NASA, UK Gov, BoE, IMF, World Bank, OECD |
| 科研/开源 | 5 | SOCKS5 | arXiv AI, arXiv ML, OpenAI, Google AI, GitHub |
| 实时信号 | 3 | SOCKS5 | Hacker News, Reddit WorldNews, Reddit Tech |
| X/Nitter | 18 | SOCKS5 | Trump, Biden, Musk, Gates, Fed, WhiteHouse, SECGov, Reuters, BBCBreaking, NASA, Kremlin, UK PM, EU Commission, ECB, IMF, World Bank, Treasury, Kevin Warsh |
| 中文央媒 | 6 | **国内直连** | 人民网, 新华网, 央视, 中国新闻网, 中国日报, 环球网 |
| **合计** | **98** | — | — |

### Nitter 源列表（18 个关键人物/机构）

```
Trump @realDonaldTrump       → nitter.freedit.eu/realDonaldTrump/rss
Biden @POTUS                 → nitter.freedit.eu/POTUS/rss
Elon Musk @elonmusk          → nitter.freedit.eu/elonmusk/rss
Bill Gates @BillGates        → nitter.freedit.eu/BillGates/rss
Fed @federalreserve          → nitter.freedit.eu/federalreserve/rss
WhiteHouse @WhiteHouse       → nitter.freedit.eu/WhiteHouse/rss
SECGov @SECGov               → nitter.freedit.eu/SECGov/rss
Reuters @Reuters             → nitter.freedit.eu/Reuters/rss
BBCBreaking @BBCBreaking     → nitter.freedit.eu/BBCBreaking/rss
NASA @NASA                   → nitter.freedit.eu/NASA/rss
Kremlin @KremlinRussia_E     → nitter.freedit.eu/KremlinRussia_E/rss
UK PM @10DowningStreet       → nitter.freedit.eu/10DowningStreet/rss
EU Commission @EU_Commission → nitter.freedit.eu/EU_Commission/rss
ECB @ECB                     → nitter.freedit.eu/ECB/rss
IMF @IMFNews                 → nitter.freedit.eu/IMFNews/rss
World Bank @WorldBank        → nitter.freedit.eu/WorldBank/rss
Treasury @USTreasury         → nitter.freedit.eu/USTreasury/rss
Kevin Warsh @KevinWarsh      → nitter.freedit.eu/KevinWarsh/rss
```

### 中文央媒源列表（6 个，国内直连）

```
人民网 时政         → people.com.cn/rss/politics.xml
新华网 时政         → xinhuanet.com/rss/politics.xml
央视新闻            → news.cctv.com/rss/
中国新闻网 时政     → chinanews.com/rss/politics.xml
中国日报 世界       → chinadaily.com.cn/rss/world_rss.xml
环球网 军事         → huanqiu.com/rss/military.xml
```

---

## 六、网络路由策略

### SOCKS5 代理

```
代理地址: 127.0.0.1:10808
适用: 国际源（所有非中文白名单域名的源）
实现: socks 库 + socket 打补丁（per-request）
```

### 国内直连白名单

以下域名不走代理，直接通过系统 HTTP 栈请求：

```
stats.gov.cn, people.com.cn, xinhuanet.com, cctv.com,
chinadaily.com.cn, chinanews.com, huanqiu.com, ce.cn,
gov.cn, pbc.gov.cn, eastmoney.com, 10jqka.com.cn,
36kr.com, huxiu.com, sspai.com, ifanr.com,
cls.cn, gelonghui.com, xueqiu.com
```

### 关键实现细节

```python
# socks 库打补丁方式（per-request，非全局）
import socks, socket
socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 10808)
socket.socket = socks.socksocket
resp = urllib.request.urlopen(url, timeout=10)
socket.socket = socket._socket  # restore
```

---

## 七、去重机制

```python
# 每个文章生成唯一ID
art_id = f"{name}::{art['url']}"  # name=源名称, art['url']=URL

# 状态文件（JSON）
~/.hermes/rss-scanner-state.json → {feed_name: [art_id1, art_id2, ...]}

# 截断策略：每源保留最近 500 条 art_id
for feed_name in state:
    state[feed_name] = state[feed_name][-500:]
```

---

## 八、Wiki 日报格式

输出位置: `~/wiki/RSS-Digest/{YYYY-MM-DD}.md`

```
# RSS 日报 — 2026-06-30

> 来源: N 篇文章 | M 个分类

## 通讯社 (X 篇)
- **[Reuters World]** Title
  摘要...
  _日期_ | [链接](url)

## 国家媒体 (X 篇)
...
---

## 金融媒体 (X 篇)
...
```

分类顺序: 通讯社 → 国家媒体 → 金融媒体 → 科技媒体 → 地缘媒体 → 政府机构 → 中文央媒 → X/Nitter → 实时信号 → 科研/开源 → 其他

---

## 九、调用方式

### 查看最新扫描报告

```bash
# 终端直接查看 JSON 报告
cat ~/.hermes/rss-scanner-report.json
```

### 查询 SQLite 存档

```bash
# 按分类查询最新文章
sqlite3 ~/.hermes/rss-archive.db \
  "SELECT date, source, title FROM rss_articles \
   WHERE category='通讯社' ORDER BY date DESC LIMIT 10;"

# 按日期统计各分类文章数
sqlite3 ~/.hermes/rss-archive.db \
  "SELECT category, COUNT(*) as cnt \
   FROM rss_articles \
   WHERE date >= date('now', '-1 day') \
   GROUP BY category ORDER BY cnt DESC;"
```

### 查看今日 Wiki 日报

```bash
cat ~/wiki/RSS-Digest/$(date +%F).md
```

### 通过 Hermes 工具调用

```python
from hermes_tools import terminal

# 获取最新报告
report_json = terminal("cat ~/.hermes/rss-scanner-report.json")

# 查询特定分类文章
result = terminal(
    'sqlite3 ~/.hermes/rss-archive.db '
    '"SELECT source, title, link FROM rss_articles '
    'WHERE category=\'金融媒体\' AND date >= date(\'now\', \'-1 day\') '
    'ORDER BY date DESC LIMIT 5;"'
)
```
