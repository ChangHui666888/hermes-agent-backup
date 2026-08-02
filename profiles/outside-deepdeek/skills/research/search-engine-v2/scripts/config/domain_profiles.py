"""config/domain_profiles.py — 域名画像知识库

核心设计思路：
  不让每个URL都跑一遍"完整降级链路"，而是先查表。
  命中已知域名画像后，直接给出"最优策略顺序"，
  提前跳过"明知会失败"的工具，不做无用调用。

单一来源原则 (2026-07-31 重构):
  - 域名策略链 (strategy_order) 和失败名单 (known_failing) 的规范默认值
    在 `news-platform-v8/config/domain_strategies.json` (与后端 admin_config.py 共享)。
  - 本文件的 KNOWN_PROFILES 只保留反爬类型/付费墙/直播等元数据。
  - get_profile 的策略顺序 = 配置中心 (pipeline-config.json, 由 config-agent 同步)
    → loader 默认 (JSON) → 通用默认, 不再有第二份硬编码策略列表。
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DomainProfile:
    domain: str
    anti_bot: str                    # none | datadome | cloudflare | unknown
    strategy_order: List[str]        # 按优先级排列，命中即停
    paywall: bool = False
    is_live_blog_domain: bool = False  # 该域名常有直播流页面
    notes: str = ""
    known_failing: List[str] = field(default_factory=list)


# ── 域名元数据 (不含策略链 — 策略在 domain_strategies.json) ──
KNOWN_PROFILES: dict[str, object] = {
    "wsj.com": dict(anti_bot="datadome", paywall=True, is_live_blog_domain=True,
                    notes="DataDome。browser 兜底(2026-07-31 selector修复后实测18.6s可用)；scrapling 必败"),
    "bloomberg.com": dict(anti_bot="datadome", paywall=True,
                          notes="2026-07-31 更新：selector 修复后 browser 实测可用，从 failing 移除作兜底"),
    "reuters.com": dict(anti_bot="datadome", paywall=True,
                        notes="DataDome。archive/jina/tavily 第三方兜底"),
    "ft.com": dict(anti_bot="datadome", paywall=True,
                   notes="FT付费墙。browser 最可靠，archive 次之"),
    "marketwatch.com": dict(anti_bot="datadome",
                            notes="DataDome。jina/tavily 第三方兜底"),
    "cnbc.com": dict(anti_bot="cloudflare",
                     notes="Cloudflare防护，Scrapling StealthyFetcher一般可绕过"),
    "investing.com": dict(anti_bot="cloudflare",
                          notes="Cloudflare强防护。browser 已标 failing，跳过节省 ~60s"),
    "investors.com": dict(anti_bot="cloudflare",
                          notes="Cloudflare强防护。browser(可能成功) → jina/tavily 兜底"),
    "seekingalpha.com": dict(anti_bot="cloudflare",
                             notes="Cloudflare强防护。browser(可能成功) → jina/tavily 兜底"),
    "businessinsider.com": dict(anti_bot="cloudflare",
                                notes="Cloudflare防护"),
    "bbc.co.uk": dict(anti_bot="cloudflare", is_live_blog_domain=True,
                      notes="direct 有时超时(SSL)，jina/tavily 兜底"),
    "dw.com": dict(anti_bot="none",
                   notes="DW 直连友好，跳过 scrapling/browser 避免挂起"),
    "apnews.com": dict(anti_bot="none", notes="AP News 友好直连"),
    "newsweek.com": dict(anti_bot="none", notes="Newsweek 无反爬，直连可达"),
    "aljazeera.com": dict(anti_bot="none",
                          notes="Al Jazeera 友好直连。archive/search_snippet 兜底视频页"),
    "theguardian.com": dict(anti_bot="none", notes="The Guardian 友好直连"),
    "bbc.com": dict(anti_bot="none", is_live_blog_domain=True, notes="BBC 友好直连"),
    "cnn.com": dict(anti_bot="none", notes="CNN 友好直连"),
    "arxiv.org": dict(anti_bot="none", notes="Hermes web_extract 对 arxiv 有原生支持"),
    "nytimes.com": dict(anti_bot="soft_paywall", paywall=True, notes="NYT软付费墙，direct偶尔可达"),
    "washingtonpost.com": dict(anti_bot="soft_paywall", paywall=True, notes="WaPo软付费墙"),
}

DEFAULT_STRATEGY_ORDER = [
    "direct",         # cost=1 ⚡  最便宜，先试
    "archive",        # cost=1 ⚡  同样便宜，常见于内容已下线
    "google_cache",   # cost=1 ⚡  搜索引擎缓存
    "jina",           # cost=2 🔶  第三方API，自带反爬绕过
    "tavily",         # cost=3 🔶  AI 搜索摘要，高价值兜底
    "search_snippet", # cost=1 ⚡  彻底兜底，拿摘要总比空手强
]


def _load_domain_defaults() -> dict:
    """读取规范默认表 (loader 已从 domain_strategies.json 加载) + 配置中心覆盖。"""
    from config.loader import load_config
    return load_config()


def get_profile(url: str) -> DomainProfile:
    """按 url 匹配域名画像。策略链来源优先级:
    配置中心 (pipeline-config.json) → loader 默认 (domain_strategies.json) → 通用默认。

    未知域名若在配置中心有 crawl.domain.{d}.strategy 覆盖, 也按其策略走 (支持任意域自定义)。
    """
    cfg = _load_domain_defaults()
    # 按域名长度降序匹配, 避免子串误匹配 (如 bbc.co.uk vs bbc.com)
    for domain in sorted(KNOWN_PROFILES, key=len, reverse=True):
        if domain in url:
            meta = KNOWN_PROFILES[domain]
            strategy = cfg.get(f"crawl.domain.{domain}.strategy")
            failing = cfg.get(f"crawl.domain.{domain}.failing")
            return DomainProfile(
                domain=domain,
                anti_bot=meta.get("anti_bot", "unknown"),
                strategy_order=list(strategy) if strategy else list(DEFAULT_STRATEGY_ORDER),
                paywall=meta.get("paywall", False),
                is_live_blog_domain=meta.get("is_live_blog_domain", False),
                notes=meta.get("notes", "") + " | 策略: 配置中心/JSON",
                known_failing=list(failing) if failing else [],
            )
    # 未知域名: 若配置中心有该域名的自定义策略, 按配置走 (旧行为恢复)
    for key, strategy in cfg.items():
        if key.startswith("crawl.domain.") and key.endswith(".strategy"):
            dom = key[len("crawl.domain."):-len(".strategy")]
            if dom and dom in url:
                failing = cfg.get(f"crawl.domain.{dom}.failing")
                return DomainProfile(
                    domain=dom,
                    anti_bot="unknown",
                    strategy_order=list(strategy) if strategy else list(DEFAULT_STRATEGY_ORDER),
                    notes="未知域名配置中心定义",
                    known_failing=list(failing) if failing else [],
                )
    return DomainProfile(
        domain="*",
        anti_bot="unknown",
        strategy_order=list(DEFAULT_STRATEGY_ORDER),
        notes="未知域名，按通用成本梯度尝试",
    )
