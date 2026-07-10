"""
skills/s07_entity.py — 实体驱动追踪 Skill

以"实体"为中心（人物/公司/事件）而非单个 URL，
自动执行：实体扩展 → 并行搜索 → 批量抽取 → 时间线排序

典型用途：
  - 马斯克舆情追踪（entity="马斯克", entity_type="person"）
  - 公司事件追踪（entity="OpenAI", entity_type="company"）
  - 政策追踪（entity="美联储加息", entity_type="event"）

内部串联 s01_discover + s05_parallel + s03_extract，
最终输出按时间倒序的"事件时间线"。
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.base import BaseSkill, SkillResult
from skills.s01_discover import DiscoverSkill
from skills.s02_rank import RankSkill
from skills.s05_parallel import ParallelExtractSkill
from skills.s03_extract import ExtractSkill


class EntityTrackSkill(BaseSkill):
    name = "entity_track"
    description = "实体驱动：扩展别名 → 并行搜索 → 批量抓取 → 时间线"

    def run(self, ctx: dict) -> SkillResult:
        entity = ctx.get("entity")
        if not entity:
            return self.fail("缺少 entity 参数")

        # ── Step 1: 搜索发现 ─────────────────────────────────────────
        discover = DiscoverSkill()
        discover.tools = self.tools
        disc_result = discover.run(ctx)
        if not disc_result.ok:
            return self.fail(f"实体搜索发现失败: {disc_result.error}")

        candidates = disc_result.data.get("candidates", [])
        if not candidates:
            return self.fail(f"实体 '{entity}' 搜索无结果")

        # ── Step 2: 排序选出 top-5 URL ───────────────────────────────
        rank = RankSkill()
        rank.tools = self.tools
        urls = []
        # 取前5个高分候选（不单独排序，由 s02_rank 处理）
        rank_result = rank.run({**ctx, "candidates": candidates})
        if rank_result.ok:
            top5 = rank_result.data.get("ranked_top5", [])
            urls = [c.get("url") for c in top5 if c.get("url")]
        else:
            urls = [c.get("url") for c in candidates[:5] if c.get("url")]

        # ── Step 3: 并行抓取 ─────────────────────────────────────────
        parallel = ParallelExtractSkill()
        parallel.tools = self.tools
        para_result = parallel.run({**ctx, "urls": urls, "parallel_mode": "all"})

        raw_results = []
        if para_result.ok:
            raw_results = para_result.data.get("results", [])

        # 串行兜底：并行未拿到任何结果时
        if not raw_results:
            extractor = ExtractSkill()
            extractor.tools = self.tools
            for url in urls[:3]:
                r = extractor.run({**ctx, "url": url})
                if r.ok:
                    raw_results.append(r.data)

        if not raw_results:
            return self.fail(f"实体 '{entity}' 所有 URL 抓取失败")

        # ── Step 4: 时间线排序 ───────────────────────────────────────
        def sort_key(item):
            s = item.get("structured") or {}
            return s.get("published_at") or item.get("article", {}).get("published_at") or ""

        timeline = sorted(raw_results, key=sort_key, reverse=True)

        return self.succeed(
            {
                "entity": entity,
                "entity_type": ctx.get("entity_type"),
                "event_tier": disc_result.data.get("event_tier"),
                "queries": disc_result.data.get("queries"),
                "timeline": timeline,
                "article_count": len(timeline),
            },
            meta={"candidate_count": len(candidates)},
        )
