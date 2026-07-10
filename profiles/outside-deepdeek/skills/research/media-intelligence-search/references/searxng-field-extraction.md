# SearXNG 字段提取参考（该实例）

## 实例信息
- **URL**: http://100.107.117.23:8080
- **版本**: 2026.6.14+b3e08f2a4
- **搜索引擎**: Bing News (news类别), DuckDuckGo (general类别)

## 重要限制

### 1. 无 `datetime` 属性
该实例的 `<article>` HTML 中**没有** `datetime="..."` 属性。日期信息以相对时间形式嵌入。

### 2. `site:` 操作符限制
- `categories=news` 下不支持 `site:`
- `categories=general` 下部分支持，但匹配的是全文而非标题级

### 3. URL 编码
查询参数中的空格**必须**用 `+` 编码。Python 拼接 `f"?q={query}"` 直接传空格会导致 0 结果。

## HTML 结构

### News 类别（Bing News）

```html
<article class="result result-default category-news">
  <!-- URL -->
  <a href="https://www.yahoo.com/..." class="url_header">
    <span class="url_i1">https://www.yahoo.com</span>       <!-- 域名 -->
    <span class="url_i2"> › news › politics › ...</span>     <!-- 路径 -->
  </a>

  <!-- 缩略图 -->
  <a class="thumbnail_link">
    <img class="thumbnail" src="..." title="...">
  </a>

  <!-- 标题 -->
  <h3><a href="...">Bill Gates Tells Congress Names Of 3 Women...</a></h3>

  <!-- 来源 + 相对时间 -->
  <div class="highlight">20 hours ago | Yahoo</div>

  <!-- 摘要 -->
  <p class="content">Congress wanted to speak with Gates...</p>

  <!-- 搜索引擎来源 -->
  <div class="engines"><span>bing news</span></div>

  <!-- 缓存链接 -->
  <a class="cache_link" href="...">cached</a>
</article>
```

### General 类别（DuckDuckGo）

```html
<article class="result result-default category-general">
  <a href="..." class="url_header">...</a>
  <h3><a href="...">Bill Gates Facts | Britannica</a></h3>
  <p class="content">...</p>
  <div class="engines"><span>duckduckgo</span></div>
  <!-- ❌ 无缩略图 -->
  <!-- ❌ 无 highlight (无日期/来源) -->
</article>
```

## 字段可用性矩阵

| 字段 | News 类别 | General 类别 | 提取方式 |
|:----|:---------|:------------|:--------|
| **标题** | ✅ | ✅ | `<h3><a>` |
| **URL** | ✅ | ✅ | `<a class="url_header">` href |
| **域名** | ✅ | ✅ | `<span class="url_i1">` |
| **路径** | ✅ | ✅ | `<span class="url_i2">` |
| **摘要** | ✅ | ✅ | `<p class="content">` |
| **来源** | ✅ | ❌ | `div.highlight` 中 `|` 右侧 |
| **相对时间** | ✅ "20 hours ago" | ❌ | `div.highlight` 中 `|` 左侧 |
| **绝对日期** | ❌ （需转换） | ❌ | 解析相对时间 + 当前时间 |
| **缩略图** | ✅ | ❌ | `<img class="thumbnail">` |
| **搜索引擎** | ✅ "bing news" | ✅ "duckduckgo" | `div.engines > span` |
| **缓存链接** | ✅ | ✅ | `<a class="cache_link">` |
| **作者** | ❌ | ❌ | 引擎不提供 |
| **语言** | ❌ | ❌ | 引擎不提供 |

## 相对时间 → 绝对日期转换

```python
import re
from datetime import datetime, timedelta

def parse_relative_time(text, base_time=None):
    """'20 hours ago' → datetime"""
    if base_time is None:
        base_time = datetime.now()
    
    m = re.match(r"(\d+)\s*(hour|minute|day|min|hr|h)\s*ago", text.lower())
    if not m:
        return None
    
    num = int(m.group(1))
    unit = m.group(2)
    
    if unit in ("hour", "hr", "h"):
        return base_time - timedelta(hours=num)
    elif unit in ("minute", "min"):
        return base_time - timedelta(minutes=num)
    elif unit in ("day",):
        return base_time - timedelta(days=num)
    
    return None
```

## Python 提取模板

```python
import re, html

def parse_searxng_article(art_html):
    """从单个 SearXNG article HTML 块提取结构化数据"""
    result = {}
    
    # URL + 域名
    um = re.search(r'<a href="(https?://[^"]+)" class="url_header"', art_html)
    result["url"] = um.group(1) if um else ""
    
    # 域名
    dm = re.search(r'<span class="url_i1">([^<]*)</span>', art_html)
    result["domain"] = dm.group(1).strip() if dm else ""
    
    # 标题
    tm = re.search(r'<h3>(.*?)</h3>', art_html, re.DOTALL)
    if tm:
        title = re.sub(r'<[^>]+>', '', tm.group(1)).strip()
        result["title"] = html.unescape(re.sub(r'\s+', ' ', title))
    
    # 摘要
    snm = re.search(r'<p class="content">(.*?)</p>', art_html, re.DOTALL)
    if snm:
        snippet = re.sub(r'<[^>]+>', '', snm.group(1)).strip()
        result["snippet"] = html.unescape(re.sub(r'\s+', ' ', snippet))
    
    # 来源 + 相对时间
    hm = re.search(r'<div class="highlight">(.*?)</div>', art_html, re.DOTALL)
    if hm:
        parts = hm.group(1).split("|")
        result["relative_time"] = parts[0].strip()
        result["source"] = parts[1].strip() if len(parts) > 1 else ""
        # 转换为绝对日期
        result["date"] = parse_relative_time(result["relative_time"])
    
    # 搜索引擎
    em = re.search(r'<div class="engines"><span>([^<]*)</span>', art_html)
    result["engine"] = em.group(1) if em else ""
    
    # 类别
    cm = re.search(r'category-(\w+)', art_html)
    result["category"] = cm.group(1) if cm else ""
    
    return result
```
