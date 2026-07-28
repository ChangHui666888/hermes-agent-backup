#!/usr/bin/env python3
"""
测试 Bloomberg 多链接抓取稳定性
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fetchers import fetch_browser, RateLimiter

urls = [
    "https://www.bloomberg.com/news/articles/2026-07-14/emerging-assets-steady-as-middle-east-tensions-spur-caution",
    "https://www.bloomberg.com/news/articles/2026-07-13/gold-holds-decline-on-renewed-hormuz-blockade-and-hawkish-fed",
    "https://www.bloomberg.com/news/videos/2026-07-14/warsh-to-move-markets-more-than-he-wants-3-minutes-mliv-video",
]

rate_limiter = RateLimiter(default_delay=2.0)
for url in urls:
    print(f"\n测试: {url}")
    result = fetch_browser(url, rate_limiter, timeout=60)
    if result and len(result) > 500:
        print(f"✅ 成功，内容长度: {len(result)}")
        # 打印前200字符
        print(f"   预览: {result[:200]}...")
    else:
        print(f"❌ 失败: {result}")