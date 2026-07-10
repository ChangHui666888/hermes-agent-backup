"""
router.py — Hermes 网页抓取系统总调度器

职责：
  1. 意图识别：根据 ctx 内容自动选择执行路径
  2. 技能串联：上游 Skill 输出自动流入下游 ctx
  3. 自动分流：WSJ → WSJSkill；实体 → EntityTrackSkill；等
  4. 多源增强：A级事件或 require_cross_check 时自动触发多源融合
  5. 全局时间校验：所有结果都附带 temporal_check

输入 ctx 字段说明：
  url               → 已知 URL，直接抓取
  query             → 查询词，走 发现→排序→抓取 流程
  entity            → 实体名，走 实体追踪 流程
  entity_type       → person|company|event
  is_live_blog      → bool，强制使用直播流解析
  require_cross_check → bool，强制多源融合
  freshness_mode    → breaking|market|analysis|default
  skip_expensive    → bool，跳过 computer_use 等高成本工具
  force_strategy_order → list，覆盖域名画像的默认策略顺序
  parallel_mode     → race|all（并行模式）
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from core.base import HermesToolbox, SkillResult
from skills import (
    DiscoverSkill, RankSkill, ExtractSkill, WSJSkill,
    ParallelExtractSkill, MultiSourceMergeSkill, EntityTrackSkill,
)
from config.domain_profiles import get_profile


class ScrapingRouter:

    def __init__(self, toolbox: HermesToolbox):
        self.tools = toolbox
        # 初始化所有 Skill，统一注入 toolbox
        self._skills = {}
        for cls in [
            DiscoverSkill, RankSkill, ExtractSkill, WSJSkill,
            ParallelExtractSkill, MultiSourceMergeSkill, EntityTrackSkill,
        ]:
            inst = cls()
            inst.tools = toolbox
            self._skills[inst.name] = inst

    def _sk(self, name: str):
        return self._skills[name]

    # ── 公共入口 ─────────────────────────────────────────────────────
    def handle(self, ctx: dict) -> dict:
        """
        单一入口，根据 ctx 自动路由到最优执行路径。
        返回 {"ok", "data", "error", "trace", "total_cost"}
        """
        trace = []

        try:
            result, trace = self._route(ctx, trace)
        except Exception as e:
            return {"ok": False, "data": {}, "error": f"Router 异常: {e}", "trace": trace}

        total_cost = sum(
            t.get("cost", 0) for t in result.cost_trace if t.get("ok")
        )
        return {
            "ok": result.ok,
            "data": result.data,
            "error": result.error,
            "trace": trace,
            "cost_trace": result.cost_trace,
            "total_cost": total_cost,
        }

    # ── 路由决策树 ────────────────────────────────────────────────────
    def _route(self, ctx: dict, trace: list) -> tuple[SkillResult, list]:

        # ─ 实体追踪 ──────────────────────────────────────────────────
        if ctx.get("entity"):
            result = self._sk("entity_track").run(ctx)
            trace.append(("entity_track", result.ok, result.error))
            return result, trace

        # ─ 纯 query（无 URL）→ 发现→排序→抓取 ──────────────────────
        if ctx.get("query") and not ctx.get("url"):
            result, trace = self._query_pipeline(ctx, trace)
            return result, trace

        # ─ 有 URL ────────────────────────────────────────────────────
        url = ctx.get("url", "")
        if not url:
            from core.base import SkillResult
            return SkillResult(
                ok=False, error="缺少 url / query / entity 任意一个参数"
            ), trace

        # WSJ 分流：走专用 Skill
        if "wsj.com" in url:
            result = self._sk("wsj").run(ctx)
            trace.append(("wsj_skill", result.ok, result.error))
        else:
            result = self._sk("extract").run(ctx)
            trace.append(("extract", result.ok, result.error))

        # 多源融合（A级事件 或 显式要求）
        if result.ok and (
            ctx.get("require_cross_check") or
            ctx.get("event_tier") == "A"
        ):
            result, trace = self._cross_check(ctx, result, trace)

        return result, trace

    def _query_pipeline(self, ctx: dict, trace: list) -> tuple[SkillResult, list]:
        """query → 发现 → 排序 → (并行)抓取 → [多源融合]"""

        # Step 1: 发现
        disc = self._sk("discover").run(ctx)
        trace.append(("discover", disc.ok, disc.error))
        if not disc.ok:
            return disc, trace

        candidates = disc.data.get("candidates", [])
        event_tier = disc.data.get("event_tier", "B")

        # Step 2: 排序
        rank_ctx = {**ctx, "candidates": candidates}
        rank = self._sk("rank").run(rank_ctx)
        trace.append(("rank", rank.ok, rank.error))

        if not rank.ok:
            return rank, trace

        # Step 3: 抓取
        top_url = rank.data["url"]
        top5_urls = [c.get("url") for c in rank.data.get("ranked_top5", []) if c.get("url")]

        # A 级事件或 require_cross_check：并行抓 top5，后续做多源融合
        if event_tier == "A" or ctx.get("require_cross_check"):
            para_ctx = {**ctx, "urls": top5_urls, "parallel_mode": "all"}
            para = self._sk("parallel_extract").run(para_ctx)
            trace.append(("parallel_extract", para.ok, para.error))
            if para.ok:
                result, trace = self._cross_check(
                    {**ctx, "event_tier": event_tier},
                    para,
                    trace,
                )
                return result, trace

        # 普通情况：直接抓最优 URL
        extract_ctx = {**ctx, "url": top_url}
        if "wsj.com" in top_url:
            result = self._sk("wsj").run(extract_ctx)
            trace.append(("wsj_skill", result.ok, result.error))
        else:
            result = self._sk("extract").run(extract_ctx)
            trace.append(("extract", result.ok, result.error))

        return result, trace

    def _cross_check(
        self, ctx: dict, prev_result: SkillResult, trace: list
    ) -> tuple[SkillResult, list]:
        """多源融合步骤（可选增强）"""
        results_list = prev_result.data.get("results", [])

        # 补充 structured 字段：并行抓取的 results 只有 content，先做 LLM 抽取
        if results_list and not any(r.get("structured") for r in results_list):
            from skills.s03_extract import EXTRACT_PROMPT
            enriched = []
            for r in results_list[:5]:
                if r.get("content") and self.tools.llm_extract:
                    try:
                        structured = self.tools.llm_extract(r["content"][:8000], EXTRACT_PROMPT)
                        enriched.append({**r, "structured": structured})
                    except Exception:
                        enriched.append(r)
                else:
                    enriched.append(r)
            results_list = enriched

        if len(results_list) < 2:
            return prev_result, trace

        merge_ctx = {**ctx, "results": results_list}
        merge = self._sk("multi_source_merge").run(merge_ctx)
        trace.append(("multi_source_merge", merge.ok, merge.error))

        if merge.ok:
            # 把融合结果挂在原结果上
            prev_result.data["merge"] = merge.data.get("merge_result")
            prev_result.data["source_count"] = merge.data.get("source_count")

        return prev_result, trace
