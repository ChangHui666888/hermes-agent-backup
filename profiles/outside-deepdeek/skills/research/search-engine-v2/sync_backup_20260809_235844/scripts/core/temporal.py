"""
core/temporal.py — 时间一致性验证引擎

解决的核心问题：搜索结果中混入了"URL是2026年但正文其实是2025年旧内容"
的文章，或 Wayback 快照时效与当前查询不匹配。

三层比对：
  1. URL 路径中提取年份   (如 /2025/06/12/xxx → 2025)
  2. 抽取结果中的 published_at 年份
  3. 标题/正文中的年份提及

全部一致 → confidence=high
部分一致 → confidence=medium + 冲突详情
任意冲突 → confidence=low + 强烈警告

陈旧预警：published_at 超过 N 天且调用方声明需要"最新内容"时，触发 stale_warning
"""

from datetime import datetime
from .base import extract_years_from, utcnow


STALE_THRESHOLD_DAYS = {
    "breaking": 1,   # 突发新闻：超过1天即陈旧
    "market": 3,     # 市场数据：超过3天
    "analysis": 90,  # 深度分析：90天内都算有效
    "default": 30,
}


def validate_temporal(
    url: str,
    title: str = "",
    published_at: str = None,  # ISO8601
    content_snippet: str = "",
    freshness_mode: str = "default",  # breaking|market|analysis|default
) -> dict:
    """
    返回 temporal_check dict：
    {
        url_years, title_years, body_years, published_year,
        year_conflict: bool,
        confidence: "high"|"medium"|"low",
        staleness_days: int|None,
        stale_warning: bool,
        conflicts: [str]     # 冲突描述，空列表表示无冲突
    }
    """
    url_years = extract_years_from(url)
    title_years = extract_years_from(title)
    body_years = extract_years_from(content_snippet[:500])  # 只扫前500字

    published_dt = None
    published_year = []
    if published_at:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                published_dt = datetime.strptime(
                    published_at.replace("Z", "+00:00"), fmt
                )
                published_year = [published_dt.year]
                break
            except ValueError:
                continue

    # ── 年份冲突检测 ──────────────────────────────────────
    conflicts = []
    all_year_groups = {
        "url": set(url_years),
        "title": set(title_years),
        "published": set(published_year),
    }
    non_empty = {k: v for k, v in all_year_groups.items() if v}

    if len(non_empty) >= 2:
        groups = list(non_empty.values())
        base = groups[0]
        for g in groups[1:]:
            if base and g and not (base & g):
                conflicts.append(
                    f"年份冲突: {dict(list(non_empty.items()))}"
                )
                break

    year_conflict = len(conflicts) > 0

    # ── 陈旧预警 ──────────────────────────────────────────
    staleness_days = None
    stale_warning = False
    if published_dt:
        now = utcnow()
        pub_naive = published_dt.replace(tzinfo=None)
        staleness_days = (now - pub_naive).days
        threshold = STALE_THRESHOLD_DAYS.get(freshness_mode, 30)
        if staleness_days > threshold:
            stale_warning = True
            conflicts.append(
                f"内容陈旧警告: 发布于 {staleness_days} 天前，"
                f"当前模式 '{freshness_mode}' 阈值为 {threshold} 天"
            )

    # ── 置信度评级 ────────────────────────────────────────
    if year_conflict:
        confidence = "low"
    elif stale_warning:
        confidence = "medium"
    else:
        confidence = "high"

    return {
        "url_years": url_years,
        "title_years": title_years,
        "body_years": body_years,
        "published_year": published_year,
        "year_conflict": year_conflict,
        "confidence": confidence,
        "staleness_days": staleness_days,
        "stale_warning": stale_warning,
        "conflicts": conflicts,
    }
