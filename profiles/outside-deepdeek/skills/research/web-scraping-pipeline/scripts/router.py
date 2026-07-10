"""
router.py — OpenClaw / Hermes 技能化系统的调度核心

职责：
  1. 根据输入意图 (有URL? 有query? 有entity? 是否需要直播页?) 自动选择初始Skill
  2. 失败时按预设降级链路自动重试 (Direct → JSRender → ArchiveFallback)
  3. 任何"新闻类"结果在返回前强制跑一次 TemporalValidation
  4. 支持多源融合 (可选) 作为最终一步

这是一个最小可运行的调度骨架，真实部署时把 base.py 中的
fetch_url / search / llm_extract / wayback_lookup 替换为真实实现即可。
"""

from skills import (
    DirectPageExtractSkill, SearchPickExtractSkill, MultiUrlCandidateSkill,
    StructuredNewsExtractionSkill, LiveBlogCardExtractionSkill,
    TemporalValidationSkill, JSRenderCrawlSkill, ArchiveFallbackSkill,
    MultiSourceMergeSkill, EntityDrivenExtractionSkill,
)


class ScrapingRouter:
    def __init__(self, *, fetch_url, search, llm_extract, wayback_lookup=None, render_fetch=None):
        self.fetch_url = fetch_url
        self.search = search
        self.llm_extract = llm_extract

        # 统一注入依赖到所有 Skill 类（简单起见用类属性，生产中建议改实例注入）
        for skill_cls in (
            DirectPageExtractSkill, SearchPickExtractSkill, MultiUrlCandidateSkill,
            StructuredNewsExtractionSkill, LiveBlogCardExtractionSkill,
            TemporalValidationSkill, JSRenderCrawlSkill, ArchiveFallbackSkill,
            MultiSourceMergeSkill, EntityDrivenExtractionSkill,
        ):
            skill_cls.fetch_url = staticmethod(fetch_url)
            skill_cls.search = staticmethod(search)
            skill_cls.llm_extract = staticmethod(llm_extract)
            skill_cls.wayback_lookup = staticmethod(wayback_lookup) if wayback_lookup else None
            skill_cls.render_fetch = staticmethod(render_fetch) if render_fetch else None

        self.direct = DirectPageExtractSkill()
        self.search_pick = SearchPickExtractSkill()
        self.candidate = MultiUrlCandidateSkill()
        self.structured = StructuredNewsExtractionSkill()
        self.live_blog = LiveBlogCardExtractionSkill()
        self.temporal = TemporalValidationSkill()
        self.js_render = JSRenderCrawlSkill()
        self.archive = ArchiveFallbackSkill()
        self.merge = MultiSourceMergeSkill()
        self.entity = EntityDrivenExtractionSkill()

    def handle(self, ctx: dict) -> dict:
        """
        ctx 输入示例：
          {"url": "...", "is_live_blog": False}
          {"query": "..."}
          {"entity": "马斯克"}
          {"url": "...", "is_live_blog": True}
        """
        trace = []

        # ---- 路由决策 ----
        if ctx.get("entity"):
            result = self.entity.run(ctx)
            trace.append(("entity_driven", result.ok))
            return self._finalize(result, trace)

        if ctx.get("query") and not ctx.get("url"):
            candidates = self.search(ctx["query"])
            ranked = self.candidate.run({"query": ctx["query"], "candidates": candidates})
            trace.append(("multi_url_candidate", ranked.ok))
            if not ranked.ok:
                return self._error(ranked.error, trace)
            ctx = {**ctx, "url": ranked.data["url"]}

        url = ctx.get("url")
        if not url:
            return self._error("无法路由：既无 url、query，也无 entity", trace)

        if ctx.get("is_live_blog"):
            result = self.live_blog.run(ctx)
            trace.append(("live_blog_cards", result.ok))
            return self._finalize(result, trace)

        # ---- 主链路 + 降级链路 ----
        result = self.structured.run(ctx)
        trace.append(("structured_news", result.ok))

        if not result.ok:
            result = self.js_render.run(ctx)
            trace.append(("js_render_fallback", result.ok))

        if not result.ok and self.archive.wayback_lookup:
            result = self.archive.run(ctx)
            trace.append(("archive_fallback", result.ok))

        if not result.ok:
            return self._error(result.error, trace)

        # ---- 强制时间校验 ----
        temporal = self.temporal.run(result.data)
        trace.append(("temporal_validation", temporal.ok))
        if temporal.ok:
            result.data.update(temporal.data)

        return self._finalize(result, trace)

    def _finalize(self, result, trace):
        return {
            "ok": result.ok,
            "data": result.data,
            "error": result.error,
            "trace": trace,
        }

    def _error(self, error, trace):
        return {"ok": False, "data": {}, "error": error, "trace": trace}
