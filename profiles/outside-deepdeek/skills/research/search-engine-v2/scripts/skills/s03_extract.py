"""
skills/s03_extract.py — 内容提取 Skill（封装 ExtractCascade + 时间校验）

单个 URL → 完整 Markdown 正文（含 strategy_used / cost_trace / temporal_check）

这是调用最频繁的核心 Skill，内部做了三件事：
  1. 调 ExtractCascade 按域名画像梯度抓取
  2. 用 LLM 做结构化抽取（标题/时间/摘要/要点）
  3. 立即跑时间校验（temporal_validation），给出 confidence 标签
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.base import BaseSkill, SkillResult
from core.cascade import ExtractCascade
from core.temporal import validate_temporal

EXTRACT_PROMPT = """
从以下网页 Markdown 内容中提取结构化数据，严格按此 JSON Schema 输出：
{
  "headline": "string",
  "subheadline": "string|null",
  "author": "string|null",
  "published_at": "ISO8601 string|null（尽量包含完整时间，无则null）",
  "updated_at": "ISO8601 string|null",
  "section": "string|null",
  "summary": "string（150字以内，中文）",
  "key_points": ["string", ...],
  "related_tickers": ["string", ...]|null
}
只输出 JSON，无任何其他文字。缺失字段填 null，不要编造。
"""


class ExtractSkill(BaseSkill):
    name = "extract"
    description = "URL → Markdown → 结构化新闻数据（含成本感知级联+时间校验）"

    def run(self, ctx: dict) -> SkillResult:
        url = ctx.get("url")
        if not url:
            return self.fail("缺少 url 参数")

        # ── 1. 级联抓取 ──────────────────────────────────────────────
        cascade = ExtractCascade(self.tools)
        content, strategy_used, cost_trace = cascade.run(url, ctx)

        if not content:
            return self.fail(
                f"所有抓取策略均失败 "
                f"(tried: {[t['strategy'] for t in cost_trace]})",
                cost_trace=cost_trace,
            )

        # ── 2. LLM 结构化抽取 ────────────────────────────────────────
        structured = None
        if self.tools.llm_extract:
            try:
                structured = self.tools.llm_extract(content[:8000], EXTRACT_PROMPT)
            except Exception as e:
                # LLM 抽取失败不阻断，退化为纯 Markdown 返回
                structured = {"_extraction_error": str(e)}

        # ── 3. 时间校验 ──────────────────────────────────────────────
        headline = (structured or {}).get("headline", "")
        published_at = (structured or {}).get("published_at")
        temporal = validate_temporal(
            url=url,
            title=headline,
            published_at=published_at,
            content_snippet=content[:500],
            freshness_mode=ctx.get("freshness_mode", "default"),
        )

        return self.succeed(
            {
                "url": url,
                "content": content,
                "strategy_used": strategy_used,
                "structured": structured,
                "temporal_check": temporal,
            },
            meta={
                "confidence": temporal["confidence"],
                "has_full_text": strategy_used != "search_snippet",
            },
            cost_trace=cost_trace,
        )
