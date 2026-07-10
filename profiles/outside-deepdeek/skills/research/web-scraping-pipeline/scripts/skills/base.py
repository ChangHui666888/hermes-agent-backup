"""
base.py — 网页抓取技能系统的基础抽象层

所有 Skill 都遵循统一接口:
    run(ctx: dict) -> SkillResult

ctx 是一个可累积的"工作上下文"，前一个 Skill 的输出会合并进下一个的输入，
这样多个 Skill 可以像管道一样串联 (pipeline)。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from datetime import datetime
import re


@dataclass
class SkillResult:
    ok: bool
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    skill_name: str = ""
    meta: dict = field(default_factory=dict)

    def merged_ctx(self, ctx: dict) -> dict:
        """把本次结果合并进上下文，供下一个 Skill 使用"""
        new_ctx = dict(ctx)
        new_ctx.update(self.data)
        new_ctx.setdefault("_trace", []).append(
            {"skill": self.skill_name, "ok": self.ok, "error": self.error}
        )
        return new_ctx


class BaseSkill:
    name: str = "base"
    description: str = ""

    # ---- 依赖注入点：真实项目中替换为实际实现 ----
    fetch_url: Callable[[str], str] = None          # HTML 抓取函数 (含headless选项)
    search: Callable[[str], list] = None             # SearXNG / 搜索引擎接口
    llm_extract: Callable[[str, str], Any] = None     # 调用 LLM 做结构化抽取
    wayback_lookup: Callable[[str], Optional[str]] = None

    def run(self, ctx: dict) -> SkillResult:
        raise NotImplementedError

    def fail(self, msg: str) -> SkillResult:
        return SkillResult(ok=False, error=msg, skill_name=self.name)

    def succeed(self, data: dict, meta: Optional[dict] = None) -> SkillResult:
        return SkillResult(ok=True, data=data, skill_name=self.name, meta=meta or {})


# ---------- 通用工具函数 ----------

YEAR_RE = re.compile(r"(20\d{2})")


def extract_years(text: str) -> list[int]:
    return [int(y) for y in YEAR_RE.findall(text or "")]


def now() -> datetime:
    return datetime.now()
