#!/usr/bin/env python3
"""SearXNG 连接性与字段完整性测试脚本
用法: python scripts/verify-searxng.py [searxng_url]
默认: http://100.107.117.23:8080
"""

import sys, re, json
from datetime import datetime, timedelta
try:
    import urllib.request, urllib.parse
    HAS_REQUEST = True
except:
    import subprocess
    HAS_REQUEST = False

SEARXNG = sys.argv[1] if len(sys.argv) > 1 else "http://100.107.117.23:8080"

# ---- 测试用例 ----
TESTS = [
    ("实体 + News + 时间", f"{SEARXNG}/search?q=Bill+Gates&language=en&time_range=week&categories=news"),
    ("实体 + General",      f"{SEARXNG}/search?q=Bill+Gates&language=all&categories=general"),
    ("中文 + General",      f"{SEARXNG}/search?q=比尔盖茨&language=all&categories=general"),
    # URL 编码错误测试（故意用空格，预期 0 条）
    ("URL 编码错误",         f"{SEARXNG}/search?q=Bill Gates&language=en&categories=news"),
]

def fetch(url):
    if HAS_REQUEST:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode()
    else:
        r = subprocess.run(["curl", "-s", "-L", "-H", "User-Agent: Mozilla/5.0", url],
                          capture_output=True, text=True, timeout=15)
        return r.stdout

def extract_fields(html):
    """提取 article 结构字段"""
    arts = re.findall(r'<article[^>]*class="result[^"]*"[^>]*>(.*?)</article>', html, re.DOTALL)
    
    results = []
    for art in arts:
        entry = {}
        
        # 标题
        tm = re.search(r'<h3>(.*?)</h3>', art, re.DOTALL)
        entry["title"] = re.sub(r'<[^>]+>', '', tm.group(1)).strip()[:80] if tm else ""
        entry["has_title"] = bool(entry["title"])
        
        # URL
        um = re.search(r'<a href="(https?://[^"]+)" class="url_header"', art)
        entry["url"] = um.group(1)[:60] if um else ""
        entry["has_url"] = bool(entry["url"])
        
        # datetime 属性
        dm = re.search(r'datetime="([^"]+)"', art)
        entry["has_datetime"] = bool(dm)
        
        # highlight (相对时间 + 来源)
        hm = re.search(r'<div class="highlight">(.*?)</div>', art, re.DOTALL)
        entry["has_highlight"] = bool(hm)
        if hm:
            txt = re.sub(r'<[^>]+>', '', hm.group(1)).strip()
            entry["highlight_text"] = txt[:50]
        
        # 缩略图
        im = re.search(r'<img class="thumbnail"', art)
        entry["has_thumbnail"] = bool(im)
        
        # 内容摘要
        snm = re.search(r'<p class="content">(.*?)</p>', art, re.DOTALL)
        entry["has_content"] = bool(snm)
        
        results.append(entry)
    
    return results

print("=" * 60)
print(f"SearXNG 连接性测试: {SEARXNG}")
print("=" * 60)

all_ok = True

for name, url in TESTS:
    print(f"\n--- [{name}] ---")
    print(f"URL: {url[:90]}")
    
    try:
        html = fetch(url)
        arts = extract_fields(html)
        
        # 粗略检查是否返回了搜索结果页
        is_search_page = "results_endpoint" in html or '<article' in html
        
        if not is_search_page:
            print(f"  ⚠️ NOT a search results page (length={len(html)})")
            all_ok = False
            continue
        
        print(f"  文章数: {len(arts)}")
        
        if len(arts) == 0:
            print(f"  ⚠️ 0 articles returned — check URL encoding / category")
            if " " in url.split("?q=")[1].split("&")[0] if "?q=" in url else False:
                print(f"  → 疑似 URL 空格未编码问题")
            all_ok = False
            continue
        
        # 字段统计
        with_title = sum(1 for a in arts if a["has_title"])
        with_url = sum(1 for a in arts if a["has_url"])
        with_datetime = sum(1 for a in arts if a["has_datetime"])
        with_highlight = sum(1 for a in arts if a["has_highlight"])
        with_thumbnail = sum(1 for a in arts if a["has_thumbnail"])
        
        print(f"  字段覆盖:")
        print(f"    有标题:     {with_title}/{len(arts)}")
        print(f"    有 URL:     {with_url}/{len(arts)}")
        print(f"    有 datetime: {with_datetime}/{len(arts)}")
        print(f"    有 highlight: {with_highlight}/{len(arts)}")
        print(f"    有缩略图:   {with_thumbnail}/{len(arts)}")
        
        if with_datetime == 0 and with_highlight > 0:
            print(f"  ℹ️ 确认：无 datetime 属性，日期信息在 highlight 中")
        elif with_datetime > 0:
            print(f"  ℹ️ datetime 属性存在！可能与本文档描述不符，请更新 references")
        
        if with_highlight > 0:
            samples = [a["highlight_text"] for a in arts[:3] if a["has_highlight"]]
            print(f"  highlight 样本: {samples}")
        
        # 前 3 条标题示例
        print(f"  标题样本:")
        for a in arts[:3]:
            print(f"    - {a['title'][:60]}")
        
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        all_ok = False

print(f"\n{'='*60}")
print(f"{'✅ ALL PASSED' if all_ok else '⚠️ SOME TESTS FAILED'}")
print(f"{'='*60}")
