#!/usr/bin/env python3
"""
batch.py — Standalone batch scraper entry point. No Agent session needed.

Runs the cascade engine against a list of URLs using ThreadPoolExecutor
for concurrent fetching. Results are written to a JSONL file.

Usage:
    # Batch extract from a list of URLs
    python batch.py --urls urls.txt --out results.jsonl

    # Single URL extraction (debug mode)
    python batch.py --url "https://www.reuters.com/article/..." --verbose

    # With LLM structured extraction
    python batch.py --urls urls.txt --out results.jsonl --llm-extract

    # Pipe URLs from stdin
    echo "https://reuters.com/..." | python batch.py --stdin --out results.jsonl

    # Cron-friendly: batch extract + summary
    python batch.py --urls important_urls.txt --out /data/daily.jsonl --no-progress
"""

import sys
import os
import json
import argparse
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

# Ensure the scripts/ directory is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from core.fetchers import (
    fetch_direct, fetch_archive, fetch_google_cache, fetch_scrapling, fetch_browser,
    fetch_search_snippet, llm_extract_structured,
    RateLimiter,
)
from config.domain_profiles import get_profile
from config.settings import get_settings
from core.temporal import validate_temporal

logger = logging.getLogger("batch")


def extract_url(
    url: str,
    rate_limiter: RateLimiter,
    settings,
    search_func=None,
    llm_api_key: str | None = None,
    llm_prompt: str | None = None,
    skip_expensive: bool = True,
) -> dict:
    """
    Extract a single URL using the cascade engine.
    Returns a result dict.
    """
    profile = get_profile(url)
    order = list(profile.strategy_order)
    failing = set(profile.known_failing)
    if skip_expensive:
        failing |= {"computer_use", "browser"}
    order = [s for s in order if s not in failing]

    cost_trace = []

    STRATEGY_FN = {
        "direct": lambda: fetch_direct(url, rate_limiter, timeout=settings.direct_timeout),
        "archive": lambda: fetch_archive(url, rate_limiter, timeout=settings.archive_timeout),
        "google_cache": lambda: fetch_google_cache(url, rate_limiter, timeout=settings.archive_timeout),
        "scrapling": lambda: fetch_scrapling(url, rate_limiter, timeout=settings.scrapling_timeout),
        "browser": lambda: fetch_browser(url, rate_limiter, timeout=settings.browser_timeout),
        "computer_use": lambda: None,  # batch mode: disabled
        "search_snippet": lambda: fetch_search_snippet(url, search_func),
    }

    COST = {"direct": 1, "archive": 1, "google_cache": 1, "search_snippet": 1, "scrapling": 2, "browser": 3, "computer_use": 5}

    content = None
    strategy_used = None

    for strategy in order:
        fn = STRATEGY_FN.get(strategy)
        if fn is None:
            continue

        attempt = {"strategy": strategy, "cost": COST.get(strategy, 0), "url": url}
        try:
            result = fn()
        except Exception as e:
            attempt["ok"] = False
            attempt["error"] = str(e)
            cost_trace.append(attempt)
            continue

        min_len = settings.min_content_len_for(profile.domain)
        if not result or len(result.strip()) < min_len:
            attempt["ok"] = False
            attempt["error"] = "内容为空/过短" if result else "返回 None"
            cost_trace.append(attempt)
            continue

        attempt["ok"] = True
        attempt["content_len"] = len(result)
        cost_trace.append(attempt)
        content = result
        strategy_used = strategy
        break

    if not content:
        return {
            "ok": False, "url": url, "error": "所有策略均失败",
            "cost_trace": cost_trace, "strategies_tried": [t["strategy"] for t in cost_trace],
        }

    # Structured extraction: 默认纯脚本，--llm-extract 时调 DeepSeek
    structured = None
    from core.extractor import extract_structured

    if llm_api_key and llm_prompt:
        structured = llm_extract_structured(
            content, llm_prompt,
            api_key=llm_api_key,
            max_chars=settings.llm_max_input_chars,
        )
    else:
        structured = extract_structured(url, content)

    # Temporal validation
    headline = (structured or {}).get("headline", "") if isinstance(structured, dict) else ""
    published_at = (structured or {}).get("published_at") if isinstance(structured, dict) else None
    temporal = validate_temporal(
        url=url, title=headline,
        published_at=published_at,
        content_snippet=content[:500],
    )

    total_cost = sum(t.get("cost", 0) for t in cost_trace if t.get("ok"))

    return {
        "ok": True,
        "url": url,
        "domain": profile.domain,
        "content": content,
        "strategy_used": strategy_used,
        "total_cost": total_cost,
        "cost_trace": cost_trace,
        "structured": structured,
        "temporal_check": temporal,
    }


def batch_extract(
    urls: list[str],
    out_path: str,
    settings=None,
    max_workers: int = 4,
    llm_api_key: str | None = None,
    llm_prompt: str | None = None,
    verbose: bool = False,
    progress: bool = True,
) -> dict:
    """Batch extract multiple URLs concurrently. Returns summary stats."""
    settings = settings or get_settings()
    rate_limiter = RateLimiter(default_delay=settings.rate_limit_default_delay)

    # Apply per-domain delays from settings
    for domain, delay in settings.domain_rate_delay.items():
        rate_limiter.set_domain_delay(domain, delay)

    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    results = []
    ok_count = 0
    fail_count = 0
    total_cost = 0
    start_time = time.monotonic()

    with open(out_path, "w", encoding="utf-8") as f:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    extract_url, url, rate_limiter, settings,
                    search_func=None,  # search_func requires external injection
                    llm_api_key=llm_api_key,
                    llm_prompt=llm_prompt,
                    skip_expensive=True,
                ): url
                for url in urls
            }

            for i, future in enumerate(as_completed(future_map), 1):
                url = future_map[future]
                try:
                    result = future.result(timeout=120)
                except Exception as e:
                    result = {"ok": False, "url": url, "error": str(e)}

                results.append(result)
                if result["ok"]:
                    ok_count += 1
                    total_cost += result.get("total_cost", 0)
                else:
                    fail_count += 1

                # Write JSONL line
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                f.flush()

                if progress:
                    print(f"\r[{i}/{len(urls)}] ✅{ok_count} ❌{fail_count}  "
                          f"cost={total_cost}  {url[:80]}", end="", file=sys.stderr)

    elapsed = time.monotonic() - start_time

    summary = {
        "total": len(urls),
        "ok": ok_count,
        "failed": fail_count,
        "total_cost": total_cost,
        "elapsed_seconds": round(elapsed, 1),
        "urls_per_second": round(len(urls) / elapsed, 2) if elapsed > 0 else 0,
        "output": out_path,
    }

    if progress:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"完成: {ok_count}/{len(urls)} 成功, {fail_count} 失败", file=sys.stderr)
        print(f"总耗时: {elapsed:.1f}s | 总成本: {total_cost} | 速率: {summary['urls_per_second']} urls/s", file=sys.stderr)
        print(f"输出: {out_path}", file=sys.stderr)

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="search-engine-v2 独立批量抓取器 — 无需 Agent 会话",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --url "https://reuters.com/article/..." --verbose
  %(prog)s --urls urls.txt --out results.jsonl
  %(prog)s --urls urls.txt --out results.jsonl --llm-extract
  echo "https://reuters.com/..." | %(prog)s --stdin --out results.jsonl
        """,
    )
    parser.add_argument("--url", help="单个 URL 提取（调试模式）")
    parser.add_argument("--urls", help="URL 列表文件，每行一个 URL")
    parser.add_argument("--stdin", action="store_true", help="从 stdin 读取 URL 列表")
    parser.add_argument("--out", default="results.jsonl", help="输出 JSONL 文件路径")
    parser.add_argument("--llm-extract", action="store_true", help="使用 LLM 做结构化抽取（需 DEEPSEEK_API_KEY）")
    parser.add_argument("--llm-prompt", help="自定义 LLM 抽取 prompt 文件路径")
    parser.add_argument("--max-workers", type=int, default=4, help="并行线程数 (default: 4)")
    parser.add_argument("--min-content-len", type=int, default=200, help="最小有效正文长度 (default: 200)")
    parser.add_argument("--rate-delay", type=float, default=1.0, help="同域名请求间隔秒数 (default: 1.0)")
    parser.add_argument("--no-progress", action="store_true", help="不显示进度条（cron 友好）")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
    args = parser.parse_args()

    # Update settings from CLI
    from config.settings import update_settings
    update_settings(
        min_content_len=args.min_content_len,
        rate_limit_default_delay=args.rate_delay,
        batch_max_workers=args.max_workers,
    )
    settings = get_settings()

    # LLM setup
    llm_api_key = None
    llm_prompt = None
    if args.llm_extract:
        llm_api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not llm_api_key:
            print("错误: --llm-extract 需要设置 DEEPSEEK_API_KEY 环境变量", file=sys.stderr)
            sys.exit(1)
        if args.llm_prompt:
            with open(args.llm_prompt, "r", encoding="utf-8") as pf:
                llm_prompt = pf.read()
        else:
            llm_prompt = """从以下网页 Markdown 内容中提取结构化数据，严格按此 JSON Schema 输出：
{"headline":"string","subheadline":"string|null","author":"string|null","published_at":"ISO8601|null","summary":"string(150字以内中文)","key_points":["string"]}
只输出 JSON。"""

    # Single URL mode
    if args.url:
        rate_limiter = RateLimiter(default_delay=settings.rate_limit_default_delay)
        result = extract_url(
            args.url, rate_limiter, settings,
            llm_api_key=llm_api_key, llm_prompt=llm_prompt,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["ok"] else 1)

    # Collect URLs
    urls = []
    if args.urls:
        with open(args.urls, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    elif args.stdin:
        urls = [line.strip() for line in sys.stdin if line.strip() and not line.startswith("#")]

    if not urls:
        print("错误: 需要 --url, --urls, 或 --stdin 提供 URL", file=sys.stderr)
        sys.exit(1)

    # Batch mode
    summary = batch_extract(
        urls, args.out, settings=settings,
        max_workers=args.max_workers,
        llm_api_key=llm_api_key, llm_prompt=llm_prompt,
        verbose=args.verbose,
        progress=not args.no_progress,
    )

    # Print summary to stdout (for piping)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
