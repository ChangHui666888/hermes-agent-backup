"""
08_archive_fallback.py — Archive Fallback Skill（历史降级）

failed extract → Wayback → restore content

适用：原页面 404 / 内容被撤下或改版 / 反爬彻底拦截时的最后兜底手段。
通过 Wayback Machine (web.archive.org) 拉取历史快照恢复内容。

注意：归档内容可能滞后，使用时应附带"数据来源为历史快照"的标注，
并结合 06_temporal_validation 检查快照时间是否仍满足时效性要求。
"""

from .base import BaseSkill, SkillResult


class ArchiveFallbackSkill(BaseSkill):
    name = "archive_fallback"
    description = "原页面失败后，从 Wayback Machine 拉取历史快照兜底"

    def run(self, ctx: dict) -> SkillResult:
        url = ctx.get("url")
        if not url:
            return self.fail("缺少 url 参数")

        if self.wayback_lookup is None:
            return self.fail("wayback_lookup 未配置")

        snapshot = self.wayback_lookup(url)
        if not snapshot:
            return self.fail("Wayback Machine 中无可用快照")

        snapshot_html = snapshot.get("html")
        snapshot_timestamp = snapshot.get("timestamp")

        if not snapshot_html:
            return self.fail("快照存在但内容为空")

        extracted = self.llm_extract(
            snapshot_html,
            prompt="提取此历史快照页面的标题、正文摘要。输出JSON。",
        )

        return self.succeed(
            {
                "url": url,
                "extracted": extracted,
                "source": "wayback_machine",
                "snapshot_timestamp": snapshot_timestamp,
            },
            meta={"strategy": "archive_fallback", "is_stale_by_design": True},
        )
