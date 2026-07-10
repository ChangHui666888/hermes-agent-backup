"""
01_direct_extract.py — Direct Page Extract（直连抓取）

URL → HTML → extract

适用：已知确切 URL 的单页面新闻 (WSJ / Reuters 单篇文章)。
特点：最快、最简单，但容易被反爬 (403/Cloudflare/验证码)，需要上层做降级处理
（例如失败后转入 07_js_render 或 08_archive_fallback）。
"""

from .base import BaseSkill, SkillResult


class DirectPageExtractSkill(BaseSkill):
    name = "direct_extract"
    description = "URL → HTML → 结构化正文抽取"

    def run(self, ctx: dict) -> SkillResult:
        url = ctx.get("url")
        if not url:
            return self.fail("缺少 url 参数")

        try:
            html = self.fetch_url(url)
        except Exception as e:
            # 抓取失败时给出明确信号，方便路由器决定是否降级到
            # JSRenderSkill 或 ArchiveFallbackSkill
            return self.fail(f"直连抓取失败: {e}")

        if not html or len(html) < 200:
            return self.fail("返回内容过短，疑似被反爬拦截/空白页")

        extracted = self.llm_extract(
            html,
            prompt=(
                "从这段网页 HTML 中提取: 标题(title)、发布时间(published_at)、"
                "正文摘要(summary, 200字以内)、正文要点(key_points: list)。"
                "只输出 JSON。"
            ),
        )

        return self.succeed(
            {"url": url, "raw_html_len": len(html), "extracted": extracted},
            meta={"strategy": "direct"},
        )
