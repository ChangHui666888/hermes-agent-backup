"""
core/cascade.py — 成本感知的策略级联引擎

这是整套系统效能最高的核心机制：
  1. 查域名画像 → 拿到该域名的最优策略顺序
  2. 剪枝「已知必败」工具（如 WSJ 上的 browser/scrapling）
  3. 逐级尝试，成功即停，不浪费任何算力
  4. 每次尝试记录 cost_trace，供后续统计调优

策略 key → Hermes 工具对应关系：
  "direct"        → tools.web_extract(url)
  "archive"       → tools.web_extract_arch(archive_url(url))
  "scrapling"     → tools.scrapling_fetch(url)
  "browser"       → tools.browser_navigate(url, {})
  "computer_use"  → tools.computer_use(url)
  "search_snippet"→ tools.web_search(url) → 取第一条摘要

MIN_CONTENT_LEN: 低于此长度认为"疑似被拦截/空白页"，继续向下尝试
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from .base import BaseSkill, SkillResult, HermesToolbox
from config.domain_profiles import get_profile
from config.settings import get_settings

COST_MAP = {
    "direct": 1, "archive": 1, "google_cache": 1, "search_snippet": 1,
    "scrapling": 2, "browser": 3, "computer_use": 5,
}


def _build_archive_url(url: str) -> str:
    """构建 Wayback Machine 最新快照 URL（使用 0 作为时间戳表示最新）"""
    return f"https://web.archive.org/web/0/{url}"


def _run_strategy(strategy: str, tools: HermesToolbox, url: str) -> str | None:
    """执行单个策略，返回 Markdown 内容或 None"""
    try:
        if strategy == "direct":
            if not tools.web_extract:
                return None
            return tools.web_extract(url)

        elif strategy == "archive":
            if not tools.web_extract_arch:
                return None
            arch_url = _build_archive_url(url)
            return tools.web_extract_arch(arch_url)

        elif strategy == "scrapling":
            if not tools.scrapling_fetch:
                return None
            return tools.scrapling_fetch(url)

        elif strategy == "browser":
            if not tools.browser_navigate:
                return None
            return tools.browser_navigate(url, {"wait_for": "networkidle"})

        elif strategy == "computer_use":
            if not tools.computer_use:
                return None
            return tools.computer_use(url)

        elif strategy == "search_snippet":
            if not tools.web_search:
                return None
            results = tools.web_search(url)
            if not results:
                return None
            top = results[0]
            # 搜索摘要兜底：至少拿到标题+摘要，在内容完全不可达时保底
            return f"# {top.get('title', '')}\n\n{top.get('snippet', '')}\n\n[注意：此为搜索摘要兜底，非完整正文]"

    except Exception as e:
        raise RuntimeError(f"[{strategy}] 执行异常: {e}") from e

    return None


class ExtractCascade:
    """
    成本感知级联执行器（不继承 BaseSkill，作为工具被其他 Skill 调用）

    使用方式：
        cascade = ExtractCascade(tools)
        content, strategy_used, cost_trace = cascade.run(url, ctx)
    """

    def __init__(self, tools: HermesToolbox):
        self.tools = tools

    def run(
        self,
        url: str,
        ctx: dict = None,
    ) -> tuple[str | None, str | None, list]:
        """
        Returns:
            (content, strategy_used, cost_trace)
            content = None 时表示所有策略均失败
        """
        ctx = ctx or {}
        profile = get_profile(url)
        settings = get_settings()
        min_len = settings.min_content_len_for(profile.domain)

        # ctx 可强制指定策略顺序（用于调试/A-B测试）
        order = ctx.get("force_strategy_order") or profile.strategy_order

        # 剪枝：去掉此域名已知必败的策略
        failing = set(profile.known_failing)
        if ctx.get("skip_expensive"):  # 可选：跳过高成本策略
            failing |= {"computer_use", "browser"}
        order = [s for s in order if s not in failing]

        cost_trace = []

        for strategy in order:
            attempt = {
                "strategy": strategy,
                "cost": COST_MAP.get(strategy, 0),
                "url": url,
            }
            try:
                content = _run_strategy(strategy, self.tools, url)
            except RuntimeError as e:
                attempt["ok"] = False
                attempt["error"] = str(e)
                cost_trace.append(attempt)
                continue

            if not content or len(content.strip()) < min_len:
                attempt["ok"] = False
                attempt["error"] = (
                    "内容为空/过短（疑似被反爬拦截）"
                    if content is not None
                    else "工具未配置或返回 None"
                )
                cost_trace.append(attempt)
                continue

            attempt["ok"] = True
            attempt["content_len"] = len(content)
            cost_trace.append(attempt)
            return content, strategy, cost_trace

        return None, None, cost_trace
