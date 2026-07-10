"""
skills/s01_discover.py — 智能搜索发现 Skill

对齐 Hermes 能力：
  - tools.web_search          → 一级广覆盖搜索（SearXNG/Bing/Google）
  - 内置事件分级逻辑           → 参考 media-intelligence-search 三级架构
  - tools.web_search(tavily)   → 二级深度搜索（A级事件触发，可选）

输出：候选 URL 列表（含分级权重和摘要），供下游 s03_rank / s02_extract 使用

两种调用模式：
  1. 普通搜索   ctx={"query": "美联储利率决议"}
  2. 实体搜索   ctx={"entity": "马斯克", "entity_type": "person"}
     → 自动展开别名 + 多 query 并行搜索（via delegate_task）
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.base import BaseSkill, SkillResult

# 实体扩展 prompt
ENTITY_EXPAND_PROMPT = """
给定实体名称和类型，生成用于新闻搜索的扩展查询列表（包含别名/英文名/相关关键词）。
返回 JSON 数组，最多5条，例如：
["马斯克", "Elon Musk", "马斯克 最新动态", "Tesla CEO news", "SpaceX Elon Musk"]
只输出 JSON 数组，不要其他文字。
"""

# 事件分级关键词（参考 media-intelligence-search）
TIER_A_SIGNALS = [
    "breaking", "breaking news", "just in", "市场崩盘", "紧急",
    "Fed rate", "美联储", "GDP", "非农", "央行", "战争", "conflict",
    "earnings", "财报", "业绩", "暴跌", "暴涨", "crash",
]


def _classify_event_tier(query: str, results: list) -> str:
    """简单分级：命中关键词 → A级（需深度分析），否则 B/C 级"""
    combined = (query + " ".join(r.get("title", "") for r in results[:3])).lower()
    if any(sig.lower() in combined for sig in TIER_A_SIGNALS):
        return "A"
    return "B"


class DiscoverSkill(BaseSkill):
    name = "discover"
    description = "三级搜索发现：广覆盖 → 事件分级 → （A级）深度搜索"

    def run(self, ctx: dict) -> SkillResult:
        entity = ctx.get("entity")
        query = ctx.get("query")

        if not query and not entity:
            return self.fail("缺少 query 或 entity 参数")

        # ── 实体模式：扩展别名 → 多查询 ───────────────────────────
        if entity:
            if self.tools.llm_extract is None:
                return self.fail("实体扩展需要 llm_extract 工具")
            queries = self.tools.llm_extract(
                f"实体: {entity}\n类型: {ctx.get('entity_type', 'unknown')}",
                ENTITY_EXPAND_PROMPT,
            )
            if not isinstance(queries, list):
                queries = [entity]
        else:
            queries = [query]

        # ── 并行搜索（有 delegate_task 时并行，否则串行）──────────
        all_results = []
        if self.tools.delegate_task and len(queries) > 1:
            # 并行搜索：每个 query 独立启动子 Agent
            tasks = [
                {"tool": "web_search", "args": {"query": q}}
                for q in queries[:5]
            ]
            parallel_results = self.tools.delegate_task(tasks)
            for r in parallel_results:
                if isinstance(r, list):
                    all_results.extend(r)
        else:
            for q in queries[:5]:
                if self.tools.web_search:
                    results = self.tools.web_search(q)
                    if results:
                        all_results.extend(results)

        if not all_results:
            return self.fail(f"搜索无结果 (queries={queries})")

        # 去重（同一 URL 可能被多个 query 命中）
        seen, deduped = set(), []
        for r in all_results:
            url = r.get("url", "")
            if url and url not in seen:
                seen.add(url)
                deduped.append(r)

        # ── 事件分级 ──────────────────────────────────────────────
        tier = _classify_event_tier(queries[0], deduped)
        meta = {"event_tier": tier, "query_count": len(queries), "raw_count": len(deduped)}

        # A 级事件：触发二级深度搜索（如 Tavily，这里用精确 query 复搜）
        if tier == "A" and self.tools.web_search:
            deep_query = f"site:wsj.com OR site:bloomberg.com OR site:reuters.com {queries[0]}"
            deep_results = self.tools.web_search(deep_query)
            for r in (deep_results or []):
                url = r.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    deduped.insert(0, r)  # 深度搜索结果优先
            meta["deep_search"] = True

        return self.succeed(
            {
                "candidates": deduped,
                "queries": queries,
                "entity": entity,
                "event_tier": tier,
            },
            meta=meta,
        )
