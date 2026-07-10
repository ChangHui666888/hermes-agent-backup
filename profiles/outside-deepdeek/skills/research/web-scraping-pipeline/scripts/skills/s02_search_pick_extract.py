"""
02_search_pick_extract.py — Search → Pick → Extract（标准流程）

query → SearXNG → choose URL → extract

适用：没有现成 URL，只有一个查询意图（如"今天美联储利率新闻"）。
这是最常用的新闻检索基础流程，后续 03/06 在此基础上加强（候选池排序、时间校验）。
"""

from .base import BaseSkill, SkillResult


class SearchPickExtractSkill(BaseSkill):
    name = "search_pick_extract"
    description = "query → 搜索引擎 → 选定URL → 抽取正文"

    def __init__(self, extractor: BaseSkill = None):
        # 复用 DirectPageExtractSkill 做最终抽取，避免重复实现
        from .s01_direct_extract import DirectPageExtractSkill

        self.extractor = extractor or DirectPageExtractSkill()

    def run(self, ctx: dict) -> SkillResult:
        query = ctx.get("query")
        if not query:
            return self.fail("缺少 query 参数")

        results = self.search(query)  # 期望: [{"url":..,"title":..,"snippet":..}, ...]
        if not results:
            return self.fail("搜索无结果")

        # 简单选择策略：取第一个非黑名单域名的结果
        # 实际项目中应换成 03_multi_url_candidate 的排序逻辑
        blacklist = ctx.get("domain_blacklist", [])
        chosen = next(
            (r for r in results if not any(b in r["url"] for b in blacklist)), results[0]
        )

        self.extractor.fetch_url = self.fetch_url
        self.extractor.llm_extract = self.llm_extract
        result = self.extractor.run({"url": chosen["url"]})

        if not result.ok:
            return self.fail(f"已选定URL但抽取失败: {result.error}")

        result.data["search_query"] = query
        result.data["candidates_count"] = len(results)
        result.skill_name = self.name
        return result
