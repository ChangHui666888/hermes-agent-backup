# Production RSS Scanner with httpx + feedparser

> 替代 news-resilient-retrieval 中描述的 `curl`+`re` 手搓方式。
> 当你需要建立一个**持续运行、去重、死源自愈**的 RSS 扫描引擎时使用此方案。

## 为什么升级

| 维度 | curl+regex（旧） | httpx+feedparser（v3.2） |
|---|---|---|
| 连接复用 | 每次 curl 新建连接 | httpx 连接池（keepalive），速度快 3-5x |
| 解析 | 手写 regex，脆 | feedparser 原生支持 RSS/Atom/RDF，自动 CDATA |
| 代理 | 手动 SOCKS5 挂 socket | `httpx.Client(proxy=PROXY)` 原生 |
| 并发 | 串行 | 14 workers ThreadPool 安全 |
| 去重 | 无 | SHA256 指纹 + SQLite UNIQUE 双重 |
| 稳定性 | 无 | 3次失败→24h quarantine 自动隔离 |
| 报告 | 无 | 标准 JSON 格式（feeds_detail, errors, duration） |

## 依赖安装

```bash
pip install httpx[socks] feedparser
```

## 核心架构

```python
FEEDS = [
    # cn 源直连，intl 源走 SOCKS5
    {"name": "...", "url": "...", "region": "cn|intl", "tier": "hot|warm|cold"},
    ...
]

def create_client(feed):
    """httpx 0.28+ compatible proxy routing"""
    use_proxy = feed.get("region") == "intl"
    try:
        # httpx >= 0.28: proxy= (单数, 接受字符串或 httpx.Proxy 对象)
        if use_proxy:
            return httpx.Client(proxy=PROXY, timeout=TIMEOUT, http2=True)
        return httpx.Client(timeout=TIMEOUT, http2=True)
    except TypeError:
        # httpx < 0.28 fallback: proxies= (复数)
        if use_proxy:
            return httpx.Client(proxies=PROXY, timeout=TIMEOUT, http2=True)
        return httpx.Client(timeout=TIMEOUT, http2=True)
```

## 关键设计

### 1. Region-based 路由

国际源走 SOCKS5，国内源直连。httpx 没有全局 socket 竞争问题（每个 Client 独立），所以并发安全。

```python
PROXY = "socks5://127.0.0.1:10808"

def needs_proxy(feed):
    return feed.get("region") == "intl"
```

### 2. 死源隔离（3-strike quarantine）

```python
def update_health(state, name, ok):
    m = state.setdefault(name, {"fail": 0, "quarantine_until": 0, "last_seen": ""})
    if ok: m["fail"] = 0
    else: m["fail"] += 1
    if m["fail"] >= 3:
        m["quarantine_until"] = now_ts() + 86400  # 24h
```

隔离的源在下次扫描中被跳过。隔离过期后自动重新尝试。

### 3. 增量解析（last_seen）

```python
if items:
    state[feed_name]["last_seen"] = items[0]["link"]
```

下次扫描时，一旦遇到此链接就 break，跳过所有旧文章。

### 4. SHA256 指纹去重

```python
def article_id(feed_name, url, title):
    return hashlib.sha256(f"{feed_name}|{url}|{title[:40]}".encode()).hexdigest()
```

结合 SQLite `UNIQUE` 约束，双重保障。

## 线程安全（重要）

旧版 RSS scanner 用 `socket.socket = socks.socksocket` 全局打补丁，在 8 个并发线程下会互相踩踏 → 正常源随机报 error。**httpx 不需要 socket monkey-patching**，它用 `httpx.Client(proxy=...)` 原生处理 SOCKS5，每个 Client 的连接独立隔离。所以 14 并发是安全的。

如果遇到旧版如此，要升级。

## 完整运行示例

```python
# 14 并发，98 个源
# cn 源直连，intl 源走代理
# 3 次失败自动隔离 24h
# 结果写入 ~/.hermes/rss-scanner-report.json

python rss-scanner.py
```

实测：98 源，17 秒完成，91 OK / 3 死 / 0 竞争失败。

## 报告格式

```json
{
  "timestamp": "...",
  "feeds_total": 98,
  "feeds_active": 94,
  "feeds_quarantined": 4,
  "feeds_ok": 91,
  "feeds_error": 3,
  "articles_new": 1319,
  "duration_sec": 17.19,
  "feeds_detail": [
    {"name": "BBC News", "status": "ok", "total": 34, "new": 2, "error": ""},
    ...
  ],
  "errors": [
    {"name": "Reuters Top", "error": "SSL: EOF..."}
  ]
}
```

## 旧表迁移（INTEGER id → TEXT sha256）

```python
# 旧版: id INTEGER PRIMARY KEY AUTOINCREMENT
# 新版: id TEXT PRIMARY KEY
# 自动检测并迁移
cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='rss_articles'")
row = cur.fetchone()
if row and "INTEGER" in (row[0] or "").upper():
    cur.execute("ALTER TABLE rss_articles RENAME TO rss_articles_old")
    # 重建表并迁移数据...
```
