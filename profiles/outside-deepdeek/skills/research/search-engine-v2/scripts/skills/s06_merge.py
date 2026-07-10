"""
skills/s06_merge.py — 多源融合 Skill（Multi-Source Merge）

对应 Hermes multi-source-research skill 的核心逻辑。

输入：多个来源的抽取结果（structured 字段）
输出：
  - consensus_facts：各家共同报道的事实点
  - conflicts：各家说法存在分歧之处
  - source_exclusive：各家独家信息
  - merged_summary：综合简报（200字以内）
  - confidence_score：整体可信度评分（来源数/一致性加权）

何时启用：
  - ctx["require_cross_check"] = True（高可靠性要求场景）
  - event_tier = "A"（重大事件自动触发）
  - 金融分析：需要 WSJ + Reuters + Bloomberg 三家核实
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.base import BaseSkill, SkillResult

MERGE_PROMPT = """
以下是多家媒体对同一事件的报道结构化数据（JSON数组，每项含source/headline/summary/key_points）。
请输出交叉验证简报，严格按此 JSON 格式：
{
  "consensus_facts": ["string", ...],
  "conflicts": ["string", ...],
  "source_exclusive": {"媒体名": ["独家信息点", ...], ...},
  "merged_summary": "string（200字以内综合简报）",
  "confidence_score": 0.0~1.0（来源越多越一致分越高）
}
只输出 JSON，不要其他文字。
"""


class MultiSourceMergeSkill(BaseSkill):
    name = "multi_source_merge"
    description = "多家媒体交叉验证融合，输出共识/冲突/独家/综合简报"

    def run(self, ctx: dict) -> SkillResult:
        # sources 可以是 s03_extract 的 structured 结果列表
        sources = ctx.get("sources", [])
        results = ctx.get("results", [])

        # 从并行抓取结果中自动提取 structured 字段
        if not sources and results:
            for r in results:
                s = r.get("structured") or r.get("article")
                url = r.get("url", "")
                if s and isinstance(s, dict):
                    # 推断来源媒体名
                    for domain in ["wsj.com", "bloomberg.com", "reuters.com", "ft.com", "cnbc.com"]:
                        if domain in url:
                            s["source"] = domain.split(".")[0].upper()
                            break
                    else:
                        s["source"] = url[:30]
                    sources.append(s)

        if len(sources) < 2:
            return self.fail(f"多源融合至少需要2个来源（当前: {len(sources)}）")

        if not self.tools.llm_extract:
            return self.fail("多源融合需要 llm_extract 工具")

        merged = self.tools.llm_extract(str(sources), MERGE_PROMPT)

        if not isinstance(merged, dict) or "merged_summary" not in merged:
            return self.fail("融合失败：LLM 未返回期望格式")

        return self.succeed(
            {
                "merge_result": merged,
                "source_count": len(sources),
                "sources": [s.get("source") for s in sources],
            },
            meta={"confidence_score": merged.get("confidence_score")},
        )
