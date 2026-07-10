# RSS Scanner 系统参考 — 数据源与调用方式

## 部署状态

| 项目 | 值 |
|------|-----|
| 调度频率 | 每 5 分钟 (`interval`) |
| 脚本路径 | `%LOCALAPPDATA%/hermes/scripts/rss-scanner.py` |
| 运行模式 | `no_agent=true` (纯 Python, 不调 LLM) |
| 覆盖源 | 98 个 (国际 74 + Nitter 18 + 中文央媒 6) |
| 网络路由 | 国际→SOCKS5 127.0.0.1:10808, 国内→直连 |

## 存储位置

| 用途 | 路径 |
|------|------|
| 去重状态 (JSON) | `~/.hermes/rss-scanner-state.json` |
| 最新扫描报告 (JSON) | `~/.hermes/rss-scanner-report.json` |
| 历史存档 (SQLite) | `~/.hermes/rss-archive.db` |
| 日报 (Markdown) | `~/wiki/RSS-Digest/{YYYY-MM-DD}.md` |

## SQLite 表结构

```sql
CREATE TABLE rss_articles (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    date       TEXT,         -- RSS pubDate (前25字符)
    category   TEXT,         -- 10分类之一
    source     TEXT NOT NULL,-- 源名称
    title      TEXT,         -- 文章标题
    summary    TEXT,         -- description (前300字符)
    link       TEXT UNIQUE,  -- 文章 URL (去重键)
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
```

## 查询示例

```bash
# 按分类查最新
sqlite3 ~/.hermes/rss-archive.db \
  "SELECT date, source, title FROM rss_articles \
   WHERE category='金融媒体' ORDER BY date DESC LIMIT 10;"

# 按日期统计
sqlite3 ~/.hermes/rss-archive.db \
  "SELECT category, COUNT(*) as cnt FROM rss_articles \
   WHERE date >= date('now', '-1 day') GROUP BY category ORDER BY cnt DESC;"
```

## 订阅源分类 (98 源)

| 大类 | 数量 | 路由 | 示例 |
|------|:----:|:----:|------|
| 通讯社 | 7 | SOCKS5 | Reuters×3, AP×2, Bloomberg×2 |
| 国家媒体 | 17 | SOCKS5 | BBC×3, CNN×2, NBC/CBS/ABC/NYT/NPR 等 |
| 金融媒体 | 11 | SOCKS5 | FT×2, WSJ×2, Economist, CNBC 等 |
| 科技媒体 | 12 | SOCKS5 | TechCrunch, The Verge, Wired 等 |
| 地缘媒体 | 5 | SOCKS5 | Guardian, DW, Al Jazeera 等 |
| 政府机构 | 11 | SOCKS5 | White House, Fed, SEC, UN 等 |
| 科研/开源 | 5 | SOCKS5 | arXiv AI/ML, OpenAI, Google AI, GitHub |
| 实时信号 | 3 | SOCKS5 | Hacker News, Reddit×2 |
| X/Nitter | 18 | SOCKS5 | Trump, Musk, Gates, Fed 等关键人物 |
| 中文央媒 | 6 | **直连** | 人民网/新华网/央视/中国新闻网/中国日报/环球网 |
