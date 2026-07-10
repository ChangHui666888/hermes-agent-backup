"""
skills/s02_rank.py — 候选 URL 打分排序

从 s01_discover 拿到候选池后，按多维度打分选出最优 URL，
避免"盲选第一条"导致选到聚合页/旧文章/无关链接。

打分维度（可调整权重）：
  + 域名权威度  (wsj/bloomberg/reuters 加分)
  + 标题与 query 词语重合度
  + URL/标题中的年份是否是当前年
  - URL 是聚合页/列表页/标签页 (减分)
  - 黑名单域名 (排除)
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.base import BaseSkill, SkillResult, extract_years_from, utcnow

AUTHORITY_SCORES = {
    "wsj.com": 4, "bloomberg.com": 4, "ft.com": 4,
    "reuters.com": 3, "apnews.com": 3, "cnbc.com": 2,
    "marketwatch.com": 2, "barrons.com": 2,
    "businessinsider.com": 1,
}

LISTING_PATTERNS = (
    "/tag/", "/topic/", "/search", "/category/",
    "/author/", "/section/", "?q=", "?s=",
)

DEFAULT_BLACKLIST = ["google.com/search", "bing.com/search", "reddit.com"]


def score_candidate(candidate: dict, query: str, current_year: int) -> float:
    url = candidate.get("url", "")
    title = candidate.get("title", "")
    snippet = candidate.get("snippet", "")
    s = 0.0

    # 域名权威度
    for domain, w in AUTHORITY_SCORES.items():
        if domain in url:
            s += w
            break

    # 聚合页/列表页降权
    if any(p in url for p in LISTING_PATTERNS):
        s -= 4

    # 标题与 query 关键词重合（简单分词，不做 NLP）
    q_words = set(query.lower().split())
    t_words = set(title.lower().split())
    s += len(q_words & t_words) * 0.6

    # 年份时效性
    years = extract_years_from(url + " " + title + " " + snippet)
    if years:
        latest = max(years)
        if latest == current_year:
            s += 2
        elif latest == current_year - 1:
            s += 0.5
        else:
            s -= 1

    return s


class RankSkill(BaseSkill):
    name = "rank"
    description = "候选URL多维度打分排序，选出最优单一URL"

    def run(self, ctx: dict) -> SkillResult:
        candidates = ctx.get("candidates", [])
        query = ctx.get("query") or ctx.get("queries", [""])[0]

        if not candidates:
            return self.fail("候选列表为空")

        blacklist = ctx.get("domain_blacklist", DEFAULT_BLACKLIST)
        filtered = [
            c for c in candidates
            if not any(b in c.get("url", "") for b in blacklist)
        ]
        if not filtered:
            filtered = candidates  # 全被过滤时退化为全量

        year = utcnow().year
        ranked = sorted(filtered, key=lambda c: score_candidate(c, query, year), reverse=True)
        best = ranked[0]

        return self.succeed(
            {
                "url": best["url"],
                "chosen_title": best.get("title"),
                "chosen_snippet": best.get("snippet"),
                "ranked_top5": ranked[:5],
            },
            meta={"pool_size": len(candidates), "filtered_size": len(filtered)},
        )
