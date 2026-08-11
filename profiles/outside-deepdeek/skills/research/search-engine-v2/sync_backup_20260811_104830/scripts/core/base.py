"""
core/base.py — 基础接口层（直接对齐 Hermes 原生工具）

与通用版本的关键差异：
  - Toolbox 的每个字段都是 Hermes 某个具体工具的薄封装
  - 字段命名直接对应文档工具名，无中间适配层
  - delegate_task 支持并行多URL抓取（Hermes 独有能力）
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from datetime import datetime
import re


# ─────────────────────────────────────────────
# Hermes Toolbox：依赖容器，按文档工具名命名
# ─────────────────────────────────────────────
@dataclass
class HermesToolbox:
    """
    对齐 Hermes 工具清单的依赖容器。
    真实部署时把 Hermes 工具函数逐一注入到对应字段即可。

    来自 Hermes 工具文档：
      web_search        → 搜索引擎查询，返回 [{"url","title","snippet"}, ...]
      web_extract       → URL → Markdown 正文 (支持PDF/arxiv)
      web_extract_arch  → web_extract(archive.org版) → Markdown (付费墙稳定绕过)
      scrapling_fetch   → execute_code + Scrapling StealthyFetcher → Markdown
      browser_navigate  → Playwright 浏览器驱动 → Markdown/截图
      computer_use      → 桌面驱动浏览器（终极兜底）→ Markdown
      delegate_task     → 启动子 Agent 并行/串行执行，返回结果列表
      llm_extract       → 对 Markdown 文本做结构化 JSON 抽取
    """
    # ---- 搜索与发现 ----
    web_search: Optional[Callable[[str], list]] = None

    # ---- 内容提取梯队（成本递增顺序）----
    web_extract: Optional[Callable[[str], str]] = None           # cost=1 ⚡
    web_extract_arch: Optional[Callable[[str], str]] = None      # cost=1 ⚡
    scrapling_fetch: Optional[Callable[[str], str]] = None       # cost=2 🔶
    browser_navigate: Optional[Callable[[str, dict], str]] = None  # cost=3 🔴
    computer_use: Optional[Callable[[str], str]] = None          # cost=5 💀

    # ---- 并行执行（Hermes 独有）----
    delegate_task: Optional[Callable[[list], list]] = None

    # ---- LLM 结构化抽取 ----
    llm_extract: Optional[Callable[[str, str], Any]] = None


# ─────────────────────────────────────────────
# SkillResult：统一返回类型
# ─────────────────────────────────────────────
@dataclass
class SkillResult:
    ok: bool
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    skill_name: str = ""
    meta: dict = field(default_factory=dict)
    cost_trace: list = field(default_factory=list)  # 记录每次尝试及其成本，用于调优

    def merged_ctx(self, ctx: dict) -> dict:
        new_ctx = dict(ctx)
        new_ctx.update(self.data)
        new_ctx.setdefault("_trace", []).append(
            {"skill": self.skill_name, "ok": self.ok, "error": self.error}
        )
        return new_ctx

    def total_cost(self) -> int:
        return sum(t.get("cost", 0) for t in self.cost_trace if t.get("ok"))


# ─────────────────────────────────────────────
# BaseSkill：所有 Skill 的基类
# ─────────────────────────────────────────────
class BaseSkill:
    name: str = "base"
    description: str = ""
    tools: HermesToolbox = None  # 由 Router 统一注入

    def run(self, ctx: dict) -> SkillResult:
        raise NotImplementedError

    def fail(self, msg: str, cost_trace: list = None) -> SkillResult:
        return SkillResult(
            ok=False, error=msg,
            skill_name=self.name, cost_trace=cost_trace or []
        )

    def succeed(self, data: dict, meta: dict = None, cost_trace: list = None) -> SkillResult:
        return SkillResult(
            ok=True, data=data, skill_name=self.name,
            meta=meta or {}, cost_trace=cost_trace or []
        )


# ─────────────────────────────────────────────
# 通用工具函数
# ─────────────────────────────────────────────
YEAR_RE = re.compile(r"(20[2-3]\d)")  # 2020-2039


def extract_years_from(text: str) -> list[int]:
    return [int(y) for y in YEAR_RE.findall(text or "")]


def utcnow() -> datetime:
    return datetime.utcnow()


# ─────────────────────────────────────────────
# StandaloneEngine：无需 Agent 的独立执行器
# ─────────────────────────────────────────────
class StandaloneEngine:
    """
    不依赖 Hermes/Agent 会话的独立执行器。
    直接使用 core/fetchers.py 中的真实网络实现，
    可以放在 cron 中无人值守运行。

    用法:
        engine = StandaloneEngine()
        result = engine.extract("https://reuters.com/...")
        results = engine.batch_extract(["url1", "url2", ...])
    """

    def __init__(
        self,
        rate_limiter=None,
        llm_api_key: str | None = None,
        skip_expensive: bool = True,
    ):
        from core.fetchers import RateLimiter
        from config.settings import get_settings

        self.settings = get_settings()
        self.rate_limiter = rate_limiter or RateLimiter(
            default_delay=self.settings.rate_limit_default_delay,
        )
        self.llm_api_key = llm_api_key
        self.skip_expensive = skip_expensive

    def extract(self, url: str, ctx: dict = None) -> dict:
        """
        提取单个 URL。返回与 SkillResult 兼容的 dict。
        """
        from core.fetchers import extract_single
        return extract_single(
            url=url,
            rate_limiter=self.rate_limiter,
            skip_expensive=self.skip_expensive,
            min_content_len=self.settings.min_content_len,
            llm_api_key=self.llm_api_key,
        )

    def batch_extract(
        self,
        urls: list[str],
        max_workers: int = 4,
        progress: bool = False,
    ) -> list[dict]:
        """
        批量提取多个 URL（ThreadPoolExecutor 并发）。
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from core.fetchers import extract_single

        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    extract_single,
                    url=url,
                    rate_limiter=self.rate_limiter,
                    skip_expensive=self.skip_expensive,
                    min_content_len=self.settings.min_content_len,
                    llm_api_key=self.llm_api_key,
                ): url
                for url in urls
            }
            for future in as_completed(future_map):
                try:
                    results.append(future.result(timeout=120))
                except Exception as e:
                    results.append({
                        "ok": False,
                        "url": future_map[future],
                        "error": str(e),
                    })
        return results
