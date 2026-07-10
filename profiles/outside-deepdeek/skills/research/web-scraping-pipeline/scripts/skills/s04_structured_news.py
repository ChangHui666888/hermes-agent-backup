"""
04_structured_news.py — Structured News Page Extraction（结构化新闻）

HTML → headline / time / cards / summary

适用：标准新闻文章页或市场行情页 (WSJ 单篇 / Bloomberg Markets)。
与 01 的区别：01 只是粗粒度提取标题+摘要；04 输出固定 Schema，
便于下游做存储/检索/展示（例如喂给前端卡片组件）。
"""

from .base import BaseSkill, SkillResult

NEWS_SCHEMA_PROMPT = """
从这段网页 HTML 中提取结构化新闻数据，严格按以下 JSON Schema 输出，
缺失字段填 null，不要编造信息：

{
  "headline": "string",
  "subheadline": "string|null",
  "author": "string|null",
  "published_at": "ISO8601 string|null",
  "updated_at": "ISO8601 string|null",
  "section": "string|null",
  "summary": "string (150字以内)",
  "body_paragraphs": ["string", ...],
  "related_tickers": ["string", ...] | null
}
只输出 JSON，不要任何额外文字。
"""


class StructuredNewsExtractionSkill(BaseSkill):
    name = "structured_news"
    description = "HTML → 固定Schema结构化新闻数据"

    def run(self, ctx: dict) -> SkillResult:
        url = ctx.get("url")
        html = ctx.get("html") or (self.fetch_url(url) if url else None)
        if not html:
            return self.fail("缺少 html 或 url")

        structured = self.llm_extract(html, prompt=NEWS_SCHEMA_PROMPT)

        # 基本校验：headline 与 summary 是必须字段
        if not structured or not structured.get("headline"):
            return self.fail("结构化抽取失败：缺少 headline")

        return self.succeed({"url": url, "news": structured})
