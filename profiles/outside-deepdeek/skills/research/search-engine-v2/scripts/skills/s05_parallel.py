"""
skills/s05_parallel.py — 并行批量抓取 Skill（利用 Hermes delegate_task）

Hermes 独有能力：delegate_task 可以启动多个子 Agent 并行执行，
这使得"同时抓取 5 个候选 URL"的总耗时接近单次抓取，而非 5 倍。

两种工作模式：
  A. 有 delegate_task → 真正并行（每个 URL 独立子 Agent）
  B. 无 delegate_task → 串行兜底（功能不打折，只是慢一些）

典型用途：
  - 多候选URL中选出第一个能成功抓取的（竞速模式）
  - 多源融合时并行拿到所有来源（汇总模式）
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.base import BaseSkill, SkillResult
from core.cascade import ExtractCascade


class ParallelExtractSkill(BaseSkill):
    name = "parallel_extract"
    description = "多URL并行抓取（利用 delegate_task），返回首个成功结果或全量结果"

    def run(self, ctx: dict) -> SkillResult:
        urls = ctx.get("urls", [])
        if not urls:
            # 如果传的是候选池，取 top-N 的 URL
            candidates = ctx.get("candidates", [])
            urls = [c["url"] for c in candidates[:5] if c.get("url")]

        if not urls:
            return self.fail("缺少 urls 参数")

        mode = ctx.get("parallel_mode", "race")  # race=竞速取第一个 / all=全量汇总

        # ── 有 delegate_task：真正并行 ──────────────────────────────
        if self.tools.delegate_task:
            tasks = [
                {
                    "skill": "extract",  # 子 Agent 执行 extract skill
                    "ctx": {"url": url, **{k: v for k, v in ctx.items() if k != "urls"}},
                }
                for url in urls
            ]
            results_raw = self.tools.delegate_task(tasks)  # 等待所有子 Agent 完成

            results = []
            for url, raw in zip(urls, results_raw or []):
                if isinstance(raw, dict) and raw.get("ok"):
                    results.append({"url": url, **raw})

            if mode == "race":
                if results:
                    return self.succeed(
                        {"result": results[0], "parallel_count": len(urls)},
                        meta={"mode": "race", "success_count": len(results)},
                    )
                return self.fail("并行抓取：所有 URL 均失败")

            return self.succeed(
                {"results": results, "parallel_count": len(urls)},
                meta={"mode": "all", "success_count": len(results)},
            )

        # ── 无 delegate_task：串行兜底 ───────────────────────────────
        cascade = ExtractCascade(self.tools)
        results = []
        cost_trace_all = []

        for url in urls:
            content, strategy, cost_trace = cascade.run(url, ctx)
            cost_trace_all.extend(cost_trace)
            if content:
                entry = {"url": url, "content": content, "strategy_used": strategy}
                results.append(entry)
                if mode == "race":
                    return self.succeed(
                        {"result": entry, "parallel_count": len(urls)},
                        meta={"mode": "race_serial_fallback"},
                        cost_trace=cost_trace_all,
                    )

        if not results:
            return self.fail("串行抓取：所有 URL 均失败", cost_trace=cost_trace_all)

        return self.succeed(
            {"results": results, "parallel_count": len(urls)},
            meta={"mode": "all_serial_fallback", "success_count": len(results)},
            cost_trace=cost_trace_all,
        )
