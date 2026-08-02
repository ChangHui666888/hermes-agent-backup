#!/usr/bin/env python3
"""
test_video_fetch.py — 视频新闻字幕抓取可靠性测试

验证级联抓取引擎能否从视频新闻页提取内嵌字幕转写。
测试源: Bloomberg / Al Jazeera / CBS News 视频。

用法:
  python test_video_fetch.py            # 测试内置样例
  python test_video_fetch.py --url <u>  # 测试指定 URL
"""

import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

TEST_URLS = [
    # Bloomberg (DataDome, 需 jina/tavily)
    "https://www.bloomberg.com/news/videos/2026-07-14/warsh-says-fed-has-no-tolerance-for-elevated-inflation-video",
    # CBS News (Cloudflare)
    "https://www.cbsnews.com/video/us-launches-barrage-of-strikes-after-irans-attempted-surprise-attack/",
    # Al Jazeera (直连友好)
    "https://www.aljazeera.com/video/newsfeed/2026/7/29/trump-meets-netanyahu-for-a-record-seventh-time",
]


def test_strategies(url: str, title: str) -> dict:
    """对单个 URL 逐个策略测试"""
    from core.fetchers import (
        fetch_direct, fetch_archive, fetch_google_cache,
        fetch_jina_reader, fetch_tavily, fetch_searxng_alt,
    )
    results = {}
    # (名称, 调用函数)
    strategies = [
        ("direct", lambda: fetch_direct(url)),
        ("archive", lambda: fetch_archive(url)),
        ("google_cache", lambda: fetch_google_cache(url)),
        ("jina", lambda: fetch_jina_reader(url, timeout=20)),
        ("tavily", lambda: fetch_tavily(url, timeout=15)),
        ("searxng_alt", lambda: fetch_searxng_alt(url, title=title, timeout=15)),
    ]
    import re
    for name, fn in strategies:
        try:
            text = fn()
            if text and len(text) > 100:
                results[name] = {
                    "ok": True,
                    "len": len(text),
                    "preview": text[:80].replace("\n", " "),
                    "has_timestamp": bool(re.search(r"\b\d+:\d{2}\b", text[:1000])),
                }
            else:
                results[name] = {"ok": False, "len": len(text or ""), "preview": ""}
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)[:60]}
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="指定测试 URL")
    parser.add_argument("--title", default="", help="URL 标题 (提升搜索策略命中)")
    args = parser.parse_args()

    urls = [(args.url, args.title)] if args.url else [(u, "") for u in TEST_URLS]

    print("=" * 60)
    print("视频新闻字幕抓取可靠性测试")
    print("=" * 60)
    overall = {"ok": 0, "fail": 0}
    for url, title in urls:
        print(f"\n▶ {url}")
        results = test_strategies(url, title)
        for name, r in results.items():
            if r.get("ok"):
                overall["ok"] += 1
                ts = "含时间戳" if r.get("has_timestamp") else ""
                print(f"  ✅ {name:12s} ({r['len']}字) {ts}")
                print(f"      {r['preview']}")
            else:
                overall["fail"] += 1
                print(f"  ❌ {name:12s} {r.get('error', '')}")
    print("\n" + "=" * 60)
    print(f"结果: 成功={overall['ok']} 失败={overall['fail']}")


if __name__ == "__main__":
    main()
