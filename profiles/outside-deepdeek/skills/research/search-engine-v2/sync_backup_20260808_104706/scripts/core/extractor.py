"""
core/extractor.py — 纯脚本结构化抽取引擎

零 LLM 依赖，100 篇文章秒级完成。
从 Markdown 正文中提取：标题 / 发布日期 / 作者 / 摘要 / 关键要点

输出格式与 llm_extract_structured() 相同：
  {"headline", "subheadline", "author", "published_at", "summary", "key_points"}

对于需要语义理解的边缘 case（如中文新闻的隐含立场、讽刺表达），
batch.py 仍需 --llm-extract 调用 DeepSeek 补充。
"""

from __future__ import annotations
import re
import json
from datetime import datetime
from urllib.parse import urlparse


# ── 日期提取 ────────────────────────────────────────────────────

# URL 路径中的日期: /2026/07/08/ 或 /2026-07-08/
_URL_DATE_RE = re.compile(r"/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/")

# 正文中的 ISO 时间戳: 2026-07-08T18:00:00Z
_ISO_DATE_RE = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)

# "Published 8 July 2026" / "Updated: July 8, 2026" / "2026年7月8日"
_PUBLISHED_DATE_RE = re.compile(
    r"(?:Published|Updated|Posted|Date)[:\s]+"
    r"(.{10,40}?)(?:\n|$)",
    re.IGNORECASE,
)

# 中文日期: 2026年7月8日
_CN_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")

# 英文月份名
_MONTHS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_EN_DATE_RE = re.compile(
    r"(\d{1,2})\s+(January|February|March|April|May|June|"
    r"July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})",
    re.IGNORECASE,
)


def _extract_published_at(url: str, content: str) -> str | None:
    """从URL和正文中提取发布日期，返回ISO8601字符串或None。"""

    # 1. URL 路径日期（最可靠）
    m = _URL_DATE_RE.search(url)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}T00:00:00Z"

    # 2. ISO 时间戳
    m = _ISO_DATE_RE.search(content)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T{m.group(4)}:{m.group(5)}:{m.group(6)}Z"

    # 3. "Published ..." 行
    m = _PUBLISHED_DATE_RE.search(content)
    if m:
        date_str = m.group(1).strip()
        # 尝试英文日期
        em = _EN_DATE_RE.search(date_str)
        if em:
            day, month_name, year = em.group(1), em.group(2), em.group(3)
            month = _MONTHS_EN.get(month_name.lower())
            if month:
                return f"{year}-{str(month).zfill(2)}-{day.zfill(2)}T00:00:00Z"

    # 4. 中文日期
    m = _CN_DATE_RE.search(content)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}T00:00:00Z"

    return None


# ── 标题提取 ────────────────────────────────────────────────────

def _extract_headline(content: str) -> str:
    """从 Markdown 内容提取标题。优先级：# 标题 > 首行非空文本。"""
    lines = content.strip().split("\n")

    # Markdown H1
    for line in lines[:10]:
        stripped = line.strip()
        if stripped.startswith("# ") and len(stripped) > 3:
            return stripped[2:].strip()

    # 首行纯文本（非链接/图片/分隔线）
    for line in lines[:5]:
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "[", "!", ">", "---", "***", "* ")):
            return stripped[:200]

    return ""


def _extract_subheadline(content: str) -> str | None:
    """提取副标题：斜体摘要行，通常紧跟在标题后。"""
    lines = content.strip().split("\n")
    for i, line in enumerate(lines[:8]):
        stripped = line.strip()
        # Markdown 斜体段落 / 粗斜体
        if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 10:
            return stripped.strip("*").strip()
    return None


# ── 作者提取 ────────────────────────────────────────────────────

_AUTHOR_RE = re.compile(
    r"(?:By|Author|Reporter|Correspondent)[:\s]+([A-Z][A-Za-z\s.'-]{3,40}?)(?:\n|[,\d]|$)",
    re.IGNORECASE,
)
# "Reporting from LOCATION, Al Jazeera's NAME"
_REPORTING_RE = re.compile(
    r"Reporting\s+from\s+\w+,\s+\w+\s+\w+\s*'?s?\s+([A-Z][A-Za-z\s]+?)(?:\s+said|\s+reported|\s*$)",
    re.IGNORECASE,
)
# "| AUTHOR" in byline line
_BYLINE_RE = re.compile(r"\|\s*(?:By\s+)?([A-Z][A-Za-z\s.'-]{3,40}?)(?:\n|$)")


def _extract_author(content: str) -> str | None:
    """从正文前 300 字符提取作者名（byline 不可能出现在文章深处）。"""
    head = content[:300]
    for pattern in [_AUTHOR_RE, _REPORTING_RE, _BYLINE_RE]:
        m = pattern.search(head)
        if m:
            name = m.group(1).strip()
            skip = {"the", "a", "an", "in", "on", "at", "it", "he", "she", "we", "they",
                    "sick", "scum", "cuckoo", "liar", "people"}
            if len(name) > 2 and name.lower() not in skip and not name.lower().startswith(("sick", "scum", "cuckoo")):
                return name
    return None


# ── 摘要提取 ────────────────────────────────────────────────────

def _extract_summary(content: str, max_chars: int = 150) -> str:
    """
    取正文前 2-3 个有意义的句子作为摘要。
    跳过标题行、byline、链接列表。
    """
    lines = content.strip().split("\n")
    sentences = []

    # 跳过前几行的标题/byline
    skip_count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 跳过 H1/H2、斜体摘要、链接列表、推荐阅读
        if stripped.startswith(("#", ">", "[", "!", "---", "***", "*Recommended", "list of")):
            skip_count += 1
            if skip_count < 5:
                continue
        else:
            skip_count = 0

        # 跳过 byline 类行
        if re.match(r"^(By|Published|Updated|Posted|- Published)", stripped, re.IGNORECASE):
            continue

        # 收集句子
        for sent in re.split(r"(?<=[.!?。！？])\s+", stripped):
            sent = sent.strip()
            if len(sent) > 10 and not sent.startswith(("*", ">", "[")):
                sentences.append(sent)

        if len(" ".join(sentences)) > max_chars:
            break

    combined = " ".join(sentences)
    if len(combined) > max_chars:
        # 截断到max_chars的最后一个完整句子边界
        cut = combined[:max_chars]
        last_period = max(cut.rfind("."), cut.rfind("。"), cut.rfind("! "), cut.rfind("？"))
        if last_period > max_chars // 2:
            combined = combined[:last_period + 1]
        else:
            combined = cut + "..."

    return combined.strip() or content[:max_chars].strip().split("\n")[0][:max_chars]


# ── 关键要点提取 ──────────────────────────────────────────────────

# 高价值信号词：引述、数据、结论
_SIGNAL_WORDS = re.compile(
    r"\b("
    r"said|announced|reported|confirmed|revealed|stated|claimed|"
    r"according to|told|warned|urged|demanded|promised|"
    r"rose|fell|surged|plunged|jumped|dropped|climbed|declined|"
    r"percent|billion|million|trillion|"
    r"表示|称|宣布|报道|证实|透露|指出|强调|警告|呼吁|"
    r"上涨|下跌|飙升|暴跌|增长|下降"
    r")\b",
    re.IGNORECASE,
)

# 数字 + 单位（统计数据）
_STATS_RE = re.compile(r"\b\d+[\d,.]*\s*(?:%|percent|billion|million|trillion|亿|万|美元|dollars?)\b", re.IGNORECASE)

# 命名实体 + 动作
_ENTITY_ACTION_RE = re.compile(
    r"\b(?:The\s+)?(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:said|announced|reported|称|表示|宣布)",
)


def _extract_key_points(content: str, max_points: int = 5) -> list[str]:
    """
    从正文中提取关键句子。策略：
    1. 包含引述/数据的句子（最优先）
    2. 包含统计数字的句子
    3. 实体+动作的句子
    取前 max_points 条去重。
    """
    # 清理 Markdown 标记
    clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", content)  # bold → plain
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)  # links → text
    clean = re.sub(r"^>\s*", "", clean, flags=re.MULTILINE)  # blockquotes

    sentences = re.split(r"(?<=[.!?。！？])\s+", clean)
    seen = set()
    points = []

    priority_sentences = []

    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 20 or len(sent) > 300:
            continue
        # 跳过纯链接、纯数字
        if sent.startswith(("http", "www", "//")):
            continue

        score = 0
        if _SIGNAL_WORDS.search(sent):
            score += 3
        if _STATS_RE.search(sent):
            score += 2
        if _ENTITY_ACTION_RE.search(sent):
            score += 1

        if score >= 1:
            priority_sentences.append((sent, score))

    # 按分数排序，去重（基于前30字符）
    priority_sentences.sort(key=lambda x: x[1], reverse=True)
    for sent, _ in priority_sentences:
        key = sent[:40]
        if key not in seen:
            seen.add(key)
            points.append(sent[:250])
        if len(points) >= max_points:
            break

    return points


# ── 主入口 ──────────────────────────────────────────────────────

def extract_structured(
    url: str,
    content: str,
    max_summary_chars: int = 150,
    max_key_points: int = 5,
) -> dict:
    """
    纯脚本结构化抽取。输出与 llm_extract_structured 相同的 JSON schema：
    {
      "headline": str,
      "subheadline": str | null,
      "author": str | null,
      "published_at": "ISO8601" | null,
      "summary": str,
      "key_points": [str, ...]
    }
    """
    return {
        "headline": _extract_headline(content),
        "subheadline": _extract_subheadline(content),
        "author": _extract_author(content),
        "published_at": _extract_published_at(url, content) or datetime.utcnow().strftime("%Y-%m-%dT00:00:00Z"),
        "summary": _extract_summary(content, max_chars=max_summary_chars),
        "key_points": _extract_key_points(content, max_points=max_key_points),
        "_extraction_method": "rule_based",
    }


# ── 性能测试 ─────────────────────────────────────────────────────

def benchmark(samples: list[tuple[str, str]], n: int = 100) -> dict:
    """对N条数据做性能基准测试。返回平均耗时和吞吐量。"""
    import time
    start = time.monotonic()
    for url, content in samples[:n]:
        extract_structured(url, content)
    elapsed = time.monotonic() - start
    return {
        "samples": min(n, len(samples)),
        "elapsed_sec": round(elapsed, 3),
        "per_article_ms": round(elapsed / min(n, len(samples)) * 1000, 2),
        "articles_per_sec": round(min(n, len(samples)) / elapsed, 1),
    }
