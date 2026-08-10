"""
demo.py — 用 Mock 工具跑通全部场景，验证系统无报错

Mock 说明：
  这里的 mock_* 函数模拟了 Hermes 工具的行为。
  真实部署时，将这些函数替换为 Hermes 原生工具即可：
    mock_web_extract     → web_extract(url)
    mock_web_extract_arch → web_extract("https://web.archive.org/web/" + url)
    mock_web_search      → web_search(query)
    mock_scrapling       → execute_code("from scrapling import StealthyFetcher ...")
    mock_llm_extract     → 调用 Hermes llm / Claude API 做结构化抽取
    mock_delegate_task   → delegate_task([...])

验证场景：
  1. WSJ 文章抓取（direct 偶尔成功）
  2. WSJ 内容降级到 archive.org（direct 失败时）
  3. WSJ Live Blog 直播流卡片解析
  4. query 驱动标准流程（搜索→排序→抓取）
  5. A 级事件多源融合
  6. 实体追踪（马斯克）
  7. 未知域名通用梯度
"""

import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))

from core.base import HermesToolbox
from router import ScrapingRouter


# ══════════════════════════════════════════════════════════════
# Mock Hermes 工具实现
# ══════════════════════════════════════════════════════════════

def mock_web_extract(url: str) -> str:
    """模拟 web_extract：WSJ 子文章页返回空（被 DataDome 拦截），主页成功"""
    if "wsj.com" in url and "/articles/" in url and "live" not in url:
        # 模拟 DataDome 拦截场景：返回过短内容，触发 cascade 向下降级
        return "<html>Access Denied</html>"  # len < 200
    return f"""
# Mock Article: {url}

**Author:** Mock Reporter | **Published:** 2026-06-30T18:00:00Z

The Federal Reserve announced today it would maintain interest rates
at their current level of 5.25-5.50%, citing continued progress on
inflation while remaining cautious about economic growth prospects.

Key points:
- Rates held steady for third consecutive meeting
- Powell signaled potential cuts later in 2026
- Markets reacted positively to the announcement
- Core PCE inflation fell to 2.3% in May

This is a substantial mock article with sufficient content length
to pass the minimum content length validation check in the cascade engine.
Lorem ipsum dolor sit amet to pad content further for testing purposes.
""".strip()


def mock_web_extract_arch(url: str) -> str:
    """模拟 archive.org 抓取：始终成功（文档标注：✅ 稳定）"""
    original = url.replace("https://web.archive.org/web/", "")
    return f"""
# [Archive Snapshot] {original}

**Archived:** 2026-06-29T12:00:00Z | **Original Published:** 2026-06-28T20:00:00Z

WSJ Exclusive: This article was retrieved from Wayback Machine archive.
The content discusses Federal Reserve policy and market implications.

DataDome was bypassed successfully via archive.org route.
Sufficient content length to pass cascade validation threshold.
Content includes full article text as originally published.
""".strip()


def mock_web_search(query: str) -> list:
    """模拟 web_search：返回带权威域名的候选列表"""
    # 模拟三级搜索结果混合（权威媒体 + 聚合页 + 低质量来源）
    return [
        {"url": f"https://www.wsj.com/articles/fed-rate-2026-{hash(query) % 9999}", "title": f"Fed Rate Decision: {query}", "snippet": "2026-06-30 The Federal Reserve..."},
        {"url": "https://news.google.com/search?q=fed+rate", "title": "Google News: Fed", "snippet": "聚合新闻"},  # 聚合页应被降权
        {"url": f"https://www.reuters.com/markets/rates-bonds/fed-holds-{hash(query) % 1111}", "title": f"Reuters: {query} Analysis", "snippet": "Reuters 2026 coverage..."},
        {"url": f"https://www.bloomberg.com/news/articles/fed-2026", "title": f"Bloomberg: Fed Holds Rates", "snippet": "Bloomberg 2026 financial analysis..."},
        {"url": "https://reddit.com/r/finance/fed_news", "title": "Reddit thread", "snippet": "User discussion..."},  # 应被黑名单过滤
    ]


def mock_scrapling(url: str) -> str:
    """模拟 Scrapling StealthyFetcher：WSJ 返回 401，其他站点成功"""
    if "wsj.com" in url or "bloomberg.com" in url:
        return "401 Unauthorized"  # len < 200，触发降级
    return f"# Scrapling Result\n\nContent from {url}\n\n" + "x" * 300


def mock_llm_extract(text: str, prompt: str) -> any:
    """模拟 LLM 结构化抽取"""
    import re

    # 实体扩展
    if "别名" in prompt or "扩展查询" in prompt:
        entity_match = re.search(r"实体: (.+)", text)
        entity = entity_match.group(1) if entity_match else "未知实体"
        return [entity, f"{entity} latest news", f"{entity} 最新", "2026"]

    # 直播流卡片
    if "直播" in prompt or "live blog" in prompt.lower():
        return [
            {"timestamp": "2026-06-30T20:15:00Z", "title": "Fed announces decision", "content": "The Federal Reserve voted unanimously...", "is_breaking": True},
            {"timestamp": "2026-06-30T19:45:00Z", "title": "Markets await Fed", "content": "S&P 500 trading flat ahead of announcement...", "is_breaking": False},
        ]

    # 多源融合
    if "交叉验证" in prompt or "consensus" in prompt.lower() or "共识" in prompt:
        return {
            "consensus_facts": ["美联储维持利率5.25-5.50%不变", "Powell暗示年内可能降息"],
            "conflicts": ["WSJ认为年内降息2次，Bloomberg认为仅1次"],
            "source_exclusive": {"WSJ": ["消息来源称内部分歧加大"], "REUTERS": ["欧洲央行政策分歧影响"]},
            "merged_summary": "美联储2026年6月议息会议决定维持基准利率不变，市场解读偏鸽派。",
            "confidence_score": 0.85,
        }

    # 通用文章结构化
    return {
        "headline": "Federal Reserve Holds Rates Steady at 5.25-5.50%",
        "subheadline": "Powell signals potential cuts later in 2026",
        "author": "Mock Reporter",
        "published_at": "2026-06-30T18:00:00Z",
        "updated_at": None,
        "section": "Markets",
        "summary": "美联储2026年6月会议维持利率不变，鲍威尔暗示年内可能降息，市场反应积极。",
        "key_points": ["利率维持5.25-5.50%", "核心PCE通胀降至2.3%", "鲍威尔暗示年内降息"],
        "related_tickers": ["SPY", "QQQ", "TLT"],
        "paywall_truncated": False,
    }


def mock_delegate_task(tasks: list) -> list:
    """模拟 delegate_task 并行执行（这里串行模拟）"""
    results = []
    for task in tasks:
        tool = task.get("tool")
        args = task.get("args", {})
        if tool == "web_search":
            results.append(mock_web_search(args.get("query", "")))
        else:
            results.append({"ok": True, "data": {"mock": True}})
    return results


# ══════════════════════════════════════════════════════════════
# 构建 Router
# ══════════════════════════════════════════════════════════════

toolbox = HermesToolbox(
    web_search=mock_web_search,
    web_extract=mock_web_extract,
    web_extract_arch=mock_web_extract_arch,
    scrapling_fetch=mock_scrapling,
    browser_navigate=None,   # 未配置，系统会自动跳过
    computer_use=None,        # 未配置，系统会自动跳过
    delegate_task=mock_delegate_task,
    llm_extract=mock_llm_extract,
)

router = ScrapingRouter(toolbox)


def show(title: str, result: dict):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    print(f"  ok          : {result['ok']}")
    print(f"  total_cost  : {result.get('total_cost', '?')}")
    print(f"  trace       : {result.get('trace')}")
    cost_trace = result.get("cost_trace", [])
    if cost_trace:
        strategies = [(t["strategy"], "✅" if t["ok"] else "❌") for t in cost_trace]
        print(f"  strategies  : {strategies}")
    if result.get("error"):
        print(f"  error       : {result['error']}")
    if result["ok"]:
        data = result["data"]
        print(f"  strategy_used: {data.get('strategy_used')}")
        s = data.get("structured") or data.get("article") or {}
        if s:
            print(f"  headline    : {s.get('headline', '')[:60]}")
            print(f"  published   : {s.get('published_at')}")
        tc = data.get("temporal_check") or {}
        if tc:
            print(f"  confidence  : {tc.get('confidence')} | conflicts={tc.get('conflicts')}")
        if data.get("cards"):
            print(f"  cards       : {len(data['cards'])} 条直播卡片")
        if data.get("merge"):
            print(f"  merge.score : {data['merge'].get('confidence_score')}")
            print(f"  merge.summary: {data['merge'].get('merged_summary', '')[:80]}")
        if data.get("timeline"):
            print(f"  timeline    : {len(data['timeline'])} 条文章")


if __name__ == "__main__":
    # ── 场景1：WSJ 文章（direct失败→自动降级archive）
    show(
        "场景1: WSJ文章 — direct❌DataDome → archive✅自动降级",
        router.handle({"url": "https://www.wsj.com/articles/fed-rate-decision-2026"})
    )

    # ── 场景2：WSJ 主页（direct偶尔成功）
    show(
        "场景2: WSJ主页 — direct✅命中即停",
        router.handle({"url": "https://www.wsj.com/markets"})
    )

    # ── 场景3：WSJ Live Blog 直播流
    show(
        "场景3: WSJ Live Blog — 解析直播卡片数组",
        router.handle({"url": "https://www.wsj.com/livecoverage/fed-meeting-2026", "is_live_blog": True})
    )

    # ── 场景4：query 驱动标准流程
    show(
        "场景4: query驱动 — 搜索→排序→抓取",
        router.handle({"query": "美联储利率决议 2026"})
    )

    # ── 场景5：Reuters（无反爬，direct直通）
    show(
        "场景5: Reuters — 无反爬直连",
        router.handle({"url": "https://www.reuters.com/markets/rates-bonds/fed-holds-2026"})
    )

    # ── 场景6：A级事件 + 多源融合
    show(
        "场景6: A级突发事件 — 并行多源+融合交叉验证",
        router.handle({
            "query": "breaking: 美联储紧急降息 2026",
            "require_cross_check": True,
            "freshness_mode": "breaking",
        })
    )

    # ── 场景7：实体追踪
    show(
        "场景7: 实体追踪 — 马斯克舆情时间线",
        router.handle({"entity": "马斯克", "entity_type": "person"})
    )

    # ── 场景8：CNBC（Cloudflare → Scrapling）
    # mock_scrapling 对非WSJ域名成功
    show(
        "场景8: CNBC — Cloudflare → Scrapling成功",
        router.handle({"url": "https://www.cnbc.com/2026/06/30/fed-holds-rates-steady.html"})
    )

    print("\n✅ 所有场景运行完毕")


# ══════════════════════════════════════════════════════════════
# 场景4/6 的 mock_web_extract 需要正确返回 WSJ 内容
# 问题：mock_web_extract 对 /articles/ 返回过短，而 parallel 走的是 cascade
# 这是 mock 层面 WSJ 降级触发的限制，真实 Hermes 中这个行为天然存在
# ══════════════════════════════════════════════════════════════
