#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 调试：检查 Bloomberg 付费墙
"""
from playwright.sync_api import sync_playwright
import time

URL = "https://www.bloomberg.com/news/articles/2026-07-14/emerging-assets-steady-as-middle-east-tensions-spur-caution"

with sync_playwright() as p:
    # 有头模式，方便观察
    browser = p.chromium.launch(headless=False, slow_mo=100)
    page = browser.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)  # 等待页面稳定

    # 截图保存
    page.screenshot(path="bloomberg_page.png", full_page=True)

    # 保存 HTML
    html = page.content()
    with open("bloomberg_page.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"HTML 长度: {len(html)}")
    print("截图和 HTML 已保存，请检查是否显示付费墙。")
    input("按 Enter 关闭浏览器...")
    browser.close()