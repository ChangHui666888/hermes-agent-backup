"""
10_entity_driven.py — Entity-Driven Extraction（实体驱动）

person/company/event → extract related pages

适用：以"实体"为中心的舆情/事件追踪（如"马斯克"、"某公司财报"），
而非以单个query或URL为起点。流程是先做实体扩展(别名/相关关键词)，
再批量搜索+排序+抽取，最后按时间线组织。
"""

from .base import BaseSkill, SkillResult

ENTITY_EXPAND_PROMPT = """
给定实体名称，生成用于新闻搜索的扩展查询列表（包含常见别名、英文名、
相关关键词，5个以内），输出 JSON 数组，例如：
["马斯克", "Elon Musk", "特斯拉 CEO", "马斯克 最新", "Elon Musk news"]
只输出数组。
"""


class EntityDrivenExtractionSkill(BaseSkill):
    name = "entity_driven"
    description = "实体 → 扩展查询 → 批量搜索抽取 → 按时间线聚合"

    def __init__(self):
        from .s03_multi_url_candidate import MultiUrlCandidateSkill
        from .s04_structured_news import StructuredNewsExtractionSkill

        self.ranker = MultiUrlCandidateSkill()
        self.extractor = StructuredNewsExtractionSkill()

    def run(self, ctx: dict) -> SkillResult:
        entity = ctx.get("entity")
        if not entity:
            return self.fail("缺少 entity 参数")

        queries = self.llm_extract(entity, prompt=ENTITY_EXPAND_PROMPT)
        if not queries:
            queries = [entity]

        all_articles = []
        for q in queries[:5]:
            candidates = self.search(q)
            if not candidates:
                continue
            self.ranker.search = self.search
            ranked = self.ranker.run({"query": q, "candidates": candidates})
            if not ranked.ok:
                continue

            self.extractor.fetch_url = self.fetch_url
            self.extractor.llm_extract = self.llm_extract
            extracted = self.extractor.run({"url": ranked.data["url"]})
            if extracted.ok:
                all_articles.append(
                    {"query": q, "url": ranked.data["url"], **extracted.data}
                )

        if not all_articles:
            return self.fail(f"未能为实体 '{entity}' 抓取到任何有效内容")

        # 按 published_at 排序形成时间线（缺失时间的排在最后）
        def sort_key(a):
            t = (a.get("news") or {}).get("published_at")
            return t or ""

        timeline = sorted(all_articles, key=sort_key, reverse=True)

        return self.succeed(
            {"entity": entity, "expanded_queries": queries, "timeline": timeline},
            meta={"article_count": len(timeline)},
        )
