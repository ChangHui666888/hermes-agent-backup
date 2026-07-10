# SearXNG HTML 结构参考（Bing News + DuckDuckGo 引擎）

> 基于 `100.107.117.23:8080` 实例 v2026.6.14 实测。
> 版本：1.0 / 2026-06-28

## 字段可用性矩阵

| 字段 | News 类别 | General 类别 | 提取方法 |
|:-----|:---------|:------------|:--------|
| 标题 | ✅ | ✅ | `<h3><a>` textContent |
| URL | ✅ | ✅ | `a.url_header` href |
| 域名显示 | ✅ | ✅ | `span.url_i1` text |
| 路径显示 | ✅ | ✅ | `span.url_i2` text |
| 摘要 | ✅ | ✅ | `p.content` text |
| 来源+时间 | ✅ | ❌ | `div.highlight` — "20 hours ago \| Yahoo" |
| 缩略图 | ✅ | ❌ | `img.thumbnail` src |
| 搜索引擎 | ✅ "bing news" | ✅ "duckduckgo" | `div.engines > span` text |
| 缓存链接 | ✅ | ✅ | `a.cache_link` href |

## 关键发现：无 `datetime` 属性

该实例的 article HTML **不存在 `datetime=` 属性**，也不使用 `<time>` 标签。  
日期信息仅通过 `div.highlight` 中的相对时间传递（News 类别）。

## News 类别原始 HTML 结构

```html
<article class="result result-default category-news">
  <!-- URL & 域名显示 -->
  <a href="https://www.yahoo.com/..." class="url_header" rel="noreferrer">
    <div class="url_wrapper">
      <span class="url_o1"><span class="url_i1">https://www.yahoo.com</span></span>
      <span class="url_o2"><span class="url_i2"> › news › politics › ...</span></span>
    </div>
  </a>

  <!-- 缩略图（news 类别有，general 无） -->
  <a class="thumbnail_link" rel="noreferrer">
    <img class="thumbnail" src="https://www.bing.com/..." title="..." loading="lazy">
  </a>

  <!-- 标题 -->
  <h3>
    <a href="..." rel="noreferrer">
      <span class="highlight">Bill</span>
      <span class="highlight">Gates</span> Tells Congress Names Of 3 Women...
    </a>
  </h3>

  <!-- 来源 + 相对时间 ★ 唯一的日期信息来源 -->
  <div class="highlight">20 hours ago | Yahoo</div>

  <!-- 摘要 -->
  <p class="content">
    Congress wanted to speak with <span class="highlight">Gates</span>...
  </p>

  <!-- 搜索引擎来源 -->
  <div class="engines">
    <span>bing news</span>
    <a class="cache_link" href="...">cached</a>
  </div>
</article>
```

## General 类别原始 HTML 结构（示例：Britannica）

```html
<article class="result result-default category-general">
  <a href="https://www.britannica.com/facts/Bill-Gates" class="url_header">
    <span class="url_i1">https://www.britannica.com</span>
  </a>
  <h3><a href="...">Bill Gates Facts | Britannica</a></h3>
  <p class="content">Bill Gates is a software developer...</p>
  <div class="engines">
    <span>duckduckgo</span>
    <a class="cache_link">cached</a>
  </div>
  <!-- 无 thumbnail -->
  <!-- 无 highlight div (= 无日期信息) -->
</article>
```

## 相对时间 → 绝对日期转换

```python
import re
from datetime import datetime, timedelta

def relative_to_absolute(relative_time: str, now: datetime = None) -> datetime:
    """将 SearXNG 相对时间转为绝对日期。
    输入: '20 hours ago', '3 hours ago', '2 days ago'
    输出: datetime 对象
    """
    if now is None:
        now = datetime.now()
    
    m = re.match(r'(\d+)\s*(hour|hours|day|days|min|mins|minute|minutes)\s*ago', relative_time.lower())
    if not m:
        return None
    
    amount = int(m.group(1))
    unit = m.group(2)
    
    if unit.startswith('hour'):
        return now - timedelta(hours=amount)
    elif unit.startswith('day'):
        return now - timedelta(days=amount)
    elif unit.startswith('min'):
        return now - timedelta(minutes=amount)
    return None
```

## 已知 General 类别的低价值域名（应过滤/降权）

| 域名 | 原因 |
|:-----|:-----|
| wikipedia.org | 百科全书，非新闻 |
| britannica.com | 百科全书 |
| forbes.com/profile | 名人简介页，非新闻 |
| hellomagazine.com | 娱乐八卦（非工作相关） |
| qq.com (传记类) | 中文旧内容 |
| 中国工程院 | 机构介绍页 |
