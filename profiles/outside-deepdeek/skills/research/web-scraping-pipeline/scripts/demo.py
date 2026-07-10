"""
demo.py — 用 Mock 依赖跑通整个 Router，验证 10 个 Skill 的串联逻辑没有bug。
真实接入时，把下面三个 mock_* 函数换成:
  - fetch_url      -> requests/httpx 直连抓取
  - search         -> SearXNG API
  - llm_extract     -> 调用 Claude/GPT 做结构化抽取 (prompt 已在各 skill 中写好)
  - wayback_lookup  -> web.archive.org API (可选)
  - render_fetch    -> Firecrawl / Playwright (可选)
"""

from router import ScrapingRouter
import json


def mock_fetch_url(url: str) -> str:
    return f"<html><body><h1>Mock article for {url}</h1><p>2026年内容正文...</p></body></html>"


def mock_search(query: str):
    return [
        {"url": "https://www.wsj.com/markets/fed-rate-2026", "title": f"{query} 最新报道", "snippet": "2026年6月"},
        {"url": "https://example.com/tag/news", "title": "旧聚合页", "snippet": "2023年"},
    ]


def mock_llm_extract(html_or_text: str, prompt: str):
    # 真实环境中：调用 Anthropic API，传入 prompt+html_or_text，解析返回JSON
    if "JSON 数组" in prompt or "JSON数组" in prompt or "数组" in prompt and "实体" in prompt:
        return ["马斯克", "Elon Musk", "特斯拉 CEO"]
    if "卡片" in prompt:
        return [{"timestamp": "2026-07-01T08:00:00", "title": "更新1", "content": "...", "is_breaking": True}]
    if "headline" in prompt:
        return {
            "headline": "美联储维持利率不变",
            "subheadline": None,
            "author": "Reuters Staff",
            "published_at": "2026-06-30T20:00:00",
            "updated_at": None,
            "section": "Markets",
            "summary": "美联储在最新会议上决定维持利率不变...",
            "body_paragraphs": ["..."],
            "related_tickers": None,
        }
    return {"title": "示例标题", "summary": "示例摘要", "key_points": ["a", "b"]}


def mock_wayback_lookup(url: str):
    return {"html": f"<html>archived {url}</html>", "timestamp": "20250101000000"}


if __name__ == "__main__":
    router = ScrapingRouter(
        fetch_url=mock_fetch_url,
        search=mock_search,
        llm_extract=mock_llm_extract,
        wayback_lookup=mock_wayback_lookup,
    )

    print("=== 场景1: query 驱动 (Skill 2+3+4+6) ===")
    out1 = router.handle({"query": "美联储利率决议"})
    print(json.dumps(out1, ensure_ascii=False, indent=2)[:1000])

    print("\n=== 场景2: 直接URL (Skill 4+6) ===")
    out2 = router.handle({"url": "https://www.reuters.com/markets/fed-2026"})
    print(json.dumps(out2, ensure_ascii=False, indent=2)[:1000])

    print("\n=== 场景3: 直播页 (Skill 5) ===")
    out3 = router.handle({"url": "https://www.wsj.com/livecoverage/fed-2026", "is_live_blog": True})
    print(json.dumps(out3, ensure_ascii=False, indent=2)[:600])

    print("\n=== 场景4: 实体驱动 (Skill 10) ===")
    out4 = router.handle({"entity": "马斯克"})
    print(json.dumps(out4, ensure_ascii=False, indent=2)[:1000])
