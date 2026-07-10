"""
03_multi_url_candidate.py — Multi-URL Candidate Selection（候选池）

query → multiple URLs → rank → best URL → extract

适用：防止"选错链接"问题——例如搜索结果里混杂了旧文章、聚合页、
无关站点。通过打分排序选出最佳候选，而不是直接取第一条。

打分维度（可按需调整权重）：
  - 域名权威度 (权威媒体加分)
  - 标题/摘要与 query 的相关度
  - 是否包含明确日期 / 是否为今年内容
  - URL 路径特征 (是否像文章页 vs 列表页/标签页)
"""

from .base import BaseSkill, SkillResult, extract_years, now

TRUSTED_DOMAINS = {
    "wsj.com": 3, "reuters.com": 3, "bloomberg.com": 3,
    "ft.com": 2, "cnbc.com": 2, "apnews.com": 2,
}

LISTING_PATTERNS = ("/tag/", "/topic/", "/search", "/category/")


class MultiUrlCandidateSkill(BaseSkill):
    name = "multi_url_candidate"
    description = "query → 候选URL池 → 打分排序 → 选出最佳URL"

    def score(self, candidate: dict, query: str) -> float:
        url = candidate.get("url", "")
        title = candidate.get("title", "")
        snippet = candidate.get("snippet", "")
        score = 0.0

        for domain, w in TRUSTED_DOMAINS.items():
            if domain in url:
                score += w
                break

        if any(p in url for p in LISTING_PATTERNS):
            score -= 3  # 列表页/聚合页降权，优先文章页

        q_terms = set(query.lower().split())
        title_terms = set(title.lower().split())
        overlap = len(q_terms & title_terms)
        score += overlap * 0.5

        years = extract_years(title + " " + snippet + " " + url)
        if years:
            score += 1 if max(years) == now().year else -1

        return score

    def run(self, ctx: dict) -> SkillResult:
        query = ctx.get("query")
        candidates = ctx.get("candidates") or self.search(query)
        if not candidates:
            return self.fail("无候选URL")

        ranked = sorted(
            candidates, key=lambda c: self.score(c, query), reverse=True
        )
        best = ranked[0]

        return self.succeed(
            {
                "query": query,
                "url": best["url"],
                "chosen_title": best.get("title"),
                "ranked_candidates": ranked[:5],
            },
            meta={"strategy": "ranked_selection", "pool_size": len(candidates)},
        )
