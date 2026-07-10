# SearXNG HTML 字段提取参考

该 SearXNG 实例（http://100.107.117.23:8080）的 HTML 输出结构。两个类别有不同的字段可用性。

## News 类别 HTML 结构核心字段

| 字段 | 提取方式 | 示例 |
|:-----|:---------|:-----|
| 标题 | `<h3><a>` textContent | "Bill Gates Tells Congress..." |
| URL | `a.url_header` href | `https://www.yahoo.com/...` |
| 域名 | `<span class="url_i1">` textContent | `https://www.yahoo.com` |
| 路径 | `<span class="url_i2">` textContent | `› news › politics › ...` |
| 摘要 | `<p class="content">` textContent, strip HTML | "Congress wanted to speak with..." |
| 来源 | `<div class="highlight">` 中 `|` 右侧部分 | "Yahoo" |
| 相对时间 | `<div class="highlight">` 中 `|` 左侧部分 | "20 hours ago" |
| 缩略图 | `<img class="thumbnail">` src | Bing CDN URL |
| 搜索引擎 | `<div class="engines"><span>` textContent | "bing news" |
| 缓存链接 | `<a class="cache_link">` href | Wayback Machine URL |

## News vs General 差异

| 特征 | News | General |
|:-----|:-----|:--------|
| 缩略图 | ✅ `<img class="thumbnail">` | ❌ 无 |
| 来源/时间 | ✅ `<div class="highlight">` | ❌ 无 |
| 典型引擎 | Bing News | DuckDuckGo |
| 日期信息 | 相对时间 ("20 hours ago") | 完全无日期 |
| 典型内容 | 时效性新闻 | 百科/简介/旧闻 |

## 该实例 HTML 关键事实

- **没有 `datetime` 属性** — 任何 article 中都无此属性
- **没有 `<time>` 标签** — 任何 article 中都无
- **唯一日期信息来源是 `<div class="highlight">`** 中的相对时间
- **General 类别返回的 Wikipedia/Britannica/Forbes 页面完全没有时间信息**

## 相对时间转绝对日期

```python
import re
from datetime import datetime, timedelta

def parse_relative_time(text: str, now: datetime = None) -> str:
    if not now:
        now = datetime.now()
    m = re.search(r"(\d+)\s*(hour|day|minute)s?\s*ago", text.lower())
    if not m:
        return ""
    n, unit = int(m.group(1)), m.group(2)
    if "hour" in unit:
        dt = now - timedelta(hours=n)
    elif "day" in unit:
        dt = now - timedelta(days=n)
    elif "minute" in unit:
        dt = now - timedelta(minutes=n)
    else:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")
```

## General 类别防旧内容黑名单

```python
STALE_DOMAINS = [
    "wikipedia.org",
    "britannica.com",
    "forbes.com",
    "investopedia.com",
    "hellomagazine.com",
]
```
