"""
09_multi_source_merge.py — Multi-Source Merge Skill（多源融合）

WSJ + Reuters + Bloomberg → merge summary

适用：高可靠性场景（金融分析/重大事件确认），需要多家媒体交叉验证，
而不是单一信源。当前标记为 optional，按需启用。

流程：
  1. 对同一事件并行执行 02_search_pick_extract（或直接给定多个URL）
  2. 对每个来源做 04_structured_news 抽取
  3. 用 LLM 做"共识与分歧"合并：共同事实 + 各家独家信息 + 矛盾点标注
"""

from .base import BaseSkill, SkillResult

MERGE_PROMPT = """
以下是多家媒体关于同一事件的报道摘要 (JSON数组，每项含source/headline/summary)。
请输出合并后的综合简报，JSON格式：
{
  "consensus_facts": ["各家一致认可的事实点", ...],
  "source_specific": {"媒体名": ["该媒体独有的信息点", ...], ...},
  "conflicts": ["各家说法存在分歧的地方，注明哪家说了什么", ...],
  "merged_summary": "综合后的简报文字 (200字以内)"
}
只输出 JSON。
"""


class MultiSourceMergeSkill(BaseSkill):
    name = "multi_source_merge"
    description = "多家媒体报道交叉验证融合，输出共识/分歧简报"

    def run(self, ctx: dict) -> SkillResult:
        sources = ctx.get("sources")  # [{"source": "WSJ", "headline":.., "summary":..}, ...]
        if not sources or len(sources) < 2:
            return self.fail("至少需要2个来源才能做融合校验")

        merged = self.llm_extract(
            str(sources), prompt=MERGE_PROMPT
        )

        if not merged or "merged_summary" not in merged:
            return self.fail("融合失败：未生成 merged_summary")

        return self.succeed(
            {"merge_result": merged, "source_count": len(sources)},
            meta={"sources": [s.get("source") for s in sources]},
        )
