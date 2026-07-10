"""
skills/s04_wsj.py — WSJ 专用 Skill（wsj-paywall-archive-scrape 的落地实现）

完全基于 Hermes 工具文档《WSJ 场景各工具对比》的实测结论实现：

  已知事实（Hermes 实测）：
    ✅ web_extract 直连：主页面偶尔可达（DataDome 有漏网之鱼）
    ✅ web_extract(archive.org)：子卡片/文章页 稳定可达
    ❌ browser_navigate：DataDome 检测，必败
    ❌ scrapling：401 直接拒绝
    ✅ computer_use：终极兜底（模拟真人，成本最高）

  策略执行顺序（硬编码，绑定 wsj.com 画像）：
    1. web_extract 直连      → 概率性成功，成本最低先试
    2. web_extract + archive → 按时间轴找最近存档（稳定）
    3. search_snippet 搜索   → 至少拿到摘要，不空手而归

  同时实现 WSJ 特有的两种内容结构：
    a. 普通文章页     → s03_extract 正常处理
    b. Live Blog 直播流 → 拆分成卡片数组（每条含时间戳+标题+内容）

  V1 时间戳校验规则（文档提到的"时间戳校验"）：
    - WSJ URL 通常含 /YYYY/MM/DD/ 路径 或 MM-DD-YYYY 格式
    - archive.org 快照 URL 含 /web/YYYYMMDD/ 时间戳
    - 两者年份必须一致，否则判定为过期快照
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.base import BaseSkill, SkillResult, extract_years_from
from core.cascade import ExtractCascade, _build_archive_url

WSJ_LIVE_PROMPT = """
这是 WSJ 直播(live blog)页面的 Markdown 内容。
请拆分成时间序事件卡片，JSON 数组，每条：
{
  "timestamp": "ISO8601 string|null",
  "title": "string|null",
  "content": "string",
  "is_breaking": true|false
}
按时间从新到旧排列。只输出 JSON 数组。
"""

WSJ_ARTICLE_PROMPT = """
从这段 WSJ 文章 Markdown 中提取：
{
  "headline": "string",
  "author": "string|null",
  "published_at": "ISO8601 string|null",
  "summary": "string（150字以内）",
  "key_points": ["string", ...],
  "related_tickers": ["string", ...]|null,
  "paywall_truncated": true|false
}
只输出 JSON。
"""

# WSJ URL 中日期的正则（支持两种格式）
# 格式A: /YYYY/MM/DD/  (如 /2025/06/30/article)
# 格式B: MM-DD-YYYY    (如 livecoverage/stock-market-today-06-30-2025)
WSJ_DATE_RE = re.compile(r"/(20[2-3]\d)/(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])/")
WSJ_DATE_ALT_RE = re.compile(r"(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])-(20[2-3]\d)")
# archive.org 快照时间戳
ARCH_TS_RE = re.compile(r"archive\.org/web/(\d{8})")


def _extract_url_year(original_url: str) -> int | None:
    """从 WSJ URL 中提取年份，支持 /YYYY/MM/DD/ 和 MM-DD-YYYY 两种格式"""
    match = WSJ_DATE_RE.search(original_url)
    if match:
        return int(match.group(1))
    match = WSJ_DATE_ALT_RE.search(original_url)
    if match:
        return int(match.group(3))
    return None


def _validate_wsj_archive_timestamp(original_url: str, archive_url: str) -> dict:
    """V1 时间戳校验：确保 archive 快照年份与 WSJ URL 路径年份一致"""
    url_year = _extract_url_year(original_url)
    arch_match = ARCH_TS_RE.search(archive_url)
    arch_year = int(arch_match.group(1)[:4]) if arch_match else None

    ok = True
    note = "无时间戳可比对"
    if url_year and arch_year:
        ok = (url_year == arch_year)
        note = (
            f"✅ 年份一致 ({url_year})"
            if ok
            else f"⚠️ 年份不一致: URL={url_year} Archive={arch_year}（可能是过期快照）"
        )

    return {"ok": ok, "url_year": url_year, "arch_year": arch_year, "note": note}


class WSJSkill(BaseSkill):
    name = "wsj"
    description = "WSJ 专用抓取：DataDome 知情规避 + archive.org 备选 + V1时间戳校验 + 直播流解析"

    def run(self, ctx: dict) -> SkillResult:
        url = ctx.get("url")
        if not url or "wsj.com" not in url:
            return self.fail("WSJSkill 仅适用于 wsj.com 域名")

        is_live = ctx.get("is_live_blog") or "live" in url.lower()

        # ── 级联抓取（wsj 画像已内置 known_failing=browser/scrapling）──
        cascade = ExtractCascade(self.tools)
        content, strategy_used, cost_trace = cascade.run(url, ctx)

        if not content:
            return self.fail(
                "WSJ 内容获取失败（direct/archive/search_snippet 均无效）",
                cost_trace=cost_trace,
            )

        # V1 时间戳校验（仅 archive 策略时有意义）
        ts_check = None
        if strategy_used == "archive" and self.tools.web_extract_arch:
            arch_url = _build_archive_url(url)
            ts_check = _validate_wsj_archive_timestamp(url, arch_url)
            if not ts_check["ok"]:
                cost_trace.append({"note": ts_check["note"], "strategy": "archive_ts_check"})

        # ── 内容结构化 ────────────────────────────────────────────────
        structured = None
        if self.tools.llm_extract:
            prompt = WSJ_LIVE_PROMPT if is_live else WSJ_ARTICLE_PROMPT
            try:
                structured = self.tools.llm_extract(content[:8000], prompt)
            except Exception as e:
                structured = {"_error": str(e)}

        result_data = {
            "url": url,
            "content": content,
            "strategy_used": strategy_used,
            "is_live_blog": is_live,
            "timestamp_check": ts_check,
        }

        if is_live:
            result_data["cards"] = structured if isinstance(structured, list) else []
            result_data["card_count"] = len(result_data["cards"])
        else:
            result_data["article"] = structured

        return self.succeed(result_data, cost_trace=cost_trace)
