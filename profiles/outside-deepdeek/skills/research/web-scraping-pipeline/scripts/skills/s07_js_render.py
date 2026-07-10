"""
07_js_render.py — JS Rendered Page Crawl（动态渲染）

headless browser → render → extract

适用：SPA 网站 / 内容由前端JS异步加载的页面 / 部分登录墙轻量绕过场景
(仅指公开可见但需JS渲染才显示的内容，不涉及破解付费墙)。

工具：Firecrawl API 或自托管 Playwright。这里提供统一接口，
实际后端可二选一，通过 ctx["render_backend"] 切换。
"""

from .base import BaseSkill, SkillResult


class JSRenderCrawlSkill(BaseSkill):
    name = "js_render_crawl"
    description = "headless浏览器渲染后抓取，适用于SPA/动态加载页面"

    # 注入点：真实实现替换为 Firecrawl SDK 调用 或 Playwright 脚本
    render_fetch = None  # Callable[[str, dict], str] -> 渲染后的HTML

    def run(self, ctx: dict) -> SkillResult:
        url = ctx.get("url")
        if not url:
            return self.fail("缺少 url 参数")

        backend = ctx.get("render_backend", "firecrawl")
        wait_selector = ctx.get("wait_selector")  # 等待某个DOM元素出现再截取

        if self.render_fetch is None:
            return self.fail(
                "render_fetch 未配置：请注入 Firecrawl 或 Playwright 的实现"
            )

        try:
            html = self.render_fetch(
                url, {"backend": backend, "wait_selector": wait_selector}
            )
        except Exception as e:
            return self.fail(f"渲染抓取失败 ({backend}): {e}")

        if not html or len(html) < 200:
            return self.fail("渲染后内容为空，可能等待选择器错误或页面拦截")

        extracted = self.llm_extract(
            html,
            prompt="提取此动态渲染页面的标题、正文摘要、关键数据点。输出JSON。",
        )

        return self.succeed(
            {"url": url, "extracted": extracted},
            meta={"strategy": "js_render", "backend": backend},
        )
