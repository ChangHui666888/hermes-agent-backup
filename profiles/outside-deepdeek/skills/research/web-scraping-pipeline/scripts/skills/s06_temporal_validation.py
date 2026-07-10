"""
06_temporal_validation.py — Temporal Validation Skill（时间验证）

URL年份 + LastUpdated + Title一致性校验

这是整套系统的核心防错能力：防止抓到"看起来是最新、实际是去年/前年"的
旧文章（典型场景：2025/2026 混淆，或Google缓存返回了历史版本）。

校验逻辑：
  1. 从 URL 路径中提取年份 (如 /2025/06/12/xxx)
  2. 从抽取出的 published_at / updated_at 提取年份
  3. 从标题/正文中提取年份提及
  4. 三者若不一致，标记 confidence='low' 并给出冲突详情
  5. 同时检查"当前系统时间"是否晚于声称的发布时间过多（陈旧内容预警）
"""

from datetime import datetime
from .base import BaseSkill, SkillResult, extract_years, now


class TemporalValidationSkill(BaseSkill):
    name = "temporal_validation"
    description = "校验URL年份/发布时间/标题年份是否一致，防止时效性错误"

    STALE_DAYS_WARN = 30  # 超过这么多天还被当作"最新"时给出警告

    def run(self, ctx: dict) -> SkillResult:
        url = ctx.get("url", "")
        news = ctx.get("news") or ctx.get("extracted") or {}
        title = news.get("headline") or news.get("title") or ""
        published_at = news.get("published_at")

        url_years = extract_years(url)
        title_years = extract_years(title)

        published_dt = None
        if published_at:
            try:
                published_dt = datetime.fromisoformat(
                    published_at.replace("Z", "+00:00")
                )
            except Exception:
                pass

        published_year = [published_dt.year] if published_dt else []

        all_year_sets = [s for s in (url_years, title_years, published_year) if s]
        conflict = False
        if len(all_year_sets) >= 2:
            base = set(all_year_sets[0])
            for s in all_year_sets[1:]:
                if base and set(s) and not (base & set(s)):
                    conflict = True

        staleness_days = None
        stale_warning = False
        if published_dt:
            staleness_days = (now() - published_dt.replace(tzinfo=None)).days
            if staleness_days > self.STALE_DAYS_WARN and ctx.get(
                "expects_breaking_news"
            ):
                stale_warning = True

        confidence = "high"
        if conflict:
            confidence = "low"
        elif stale_warning:
            confidence = "medium"

        return self.succeed(
            {
                "temporal_check": {
                    "url_years": url_years,
                    "title_years": title_years,
                    "published_year": published_year,
                    "year_conflict": conflict,
                    "staleness_days": staleness_days,
                    "stale_warning": stale_warning,
                    "confidence": confidence,
                }
            },
            meta={"pass": confidence != "low"},
        )
