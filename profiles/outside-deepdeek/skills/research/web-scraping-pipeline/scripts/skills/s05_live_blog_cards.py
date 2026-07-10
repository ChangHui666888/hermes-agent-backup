"""
05_live_blog_cards.py — Live Blog Card Extraction（卡片流）

page → card[] → event stream

适用：WSJ/Reuters 的"live coverage"页面，内容是按时间倒序排列的
更新卡片(每条带时间戳+小标题+正文)。需要把整页拆解成事件数组，
而不是当成单篇文章处理（否则会把多条更新糅成一团）。
"""

from .base import BaseSkill, SkillResult

CARD_PROMPT = """
这是一个新闻直播(live blog)页面的HTML。请把页面拆分成多条独立的更新卡片，
按时间从新到旧排列，每条卡片输出：
{
  "timestamp": "ISO8601 string|null",
  "title": "string|null",
  "content": "string",
  "is_breaking": true|false
}
返回 JSON 数组，只输出数组本身。
"""


class LiveBlogCardExtractionSkill(BaseSkill):
    name = "live_blog_cards"
    description = "直播页 → 时间序事件卡片数组"

    def run(self, ctx: dict) -> SkillResult:
        url = ctx.get("url")
        html = ctx.get("html") or (self.fetch_url(url) if url else None)
        if not html:
            return self.fail("缺少 html 或 url")

        cards = self.llm_extract(html, prompt=CARD_PROMPT)
        if not isinstance(cards, list) or len(cards) == 0:
            return self.fail("未能解析出任何卡片，可能不是直播页结构")

        return self.succeed(
            {"url": url, "cards": cards, "card_count": len(cards)},
            meta={"latest_card": cards[0]},
        )
