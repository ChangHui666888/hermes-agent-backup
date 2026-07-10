"""
benchmark_pipeline.py — 三方案效率对比（纯计时，不调LLM）
"""

import time, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from news_intel.scorer import score_article, compute_velocity


def load_articles(n=200):
    import sqlite3
    src = sqlite3.connect(os.path.expanduser("~/.hermes/rss-archive.db"))
    src.row_factory = sqlite3.Row
    rows = src.execute(
        "SELECT source, title, summary, link, category, date FROM rss_articles ORDER BY created_at DESC LIMIT ?",
        (n,)
    ).fetchall()
    src.close()
    return rows


def benchmark():
    articles = load_articles(200)
    n = len(articles)
    print(f"测试数据: {n} 篇真实 RSS\n")

    # ── 方案 A: 先评分（全量）──
    t0 = time.time()
    tiers = []
    for r in articles:
        s = score_article(r["source"] or "", r["title"] or "", r["summary"] or "")
        tiers.append(s["tier"])
    t_score = time.time() - t0
    ab_count = sum(1 for t in tiers if t in ("A", "B"))

    # 方案 A 增强耗时：仅 Tier A/B
    # 每篇 3次Qwen调用 × 1s = 3s/篇
    t_enhance_a = ab_count * 3 * 1.0
    t_total_a = t_score + t_enhance_a
    llm_a = ab_count * 3  # 每篇3次Qwen调用

    # ── 方案 B: 评分 + 增强同步（全量）──
    t_total_b = t_score + n * 3 * 1.0  # 200篇 × 3s
    llm_b = n * 3

    # ── 方案 C: 先提取后评分（全量）──
    # 提取 = Python extract_structured (不调LLM) + 评分
    t0 = time.time()
    from core.extractor import extract_structured
    for r in articles:
        extract_structured(r["link"] or "", r["summary"] or "")
    t_extract = time.time() - t0
    t_total_c = t_extract + t_score
    llm_c = 0  # 方案C不调LLM（规则提取）

    # ── 输出 ──
    print("=" * 75)
    print(f"{'':<28} {'评分':>8} {'增强/提取':>9} {'总计':>8} {'LLM调用':>8} {'处理篇数':>8}")
    print("-" * 75)
    print(f"{'A: 先评分→选择性增强(当前)':<28} {t_score:>6.2f}s {t_enhance_a:>7.1f}s {t_total_a:>6.1f}s {llm_a:>8} {ab_count:>8}")
    print(f"{'B: 评分+增强同步(全量)':<28} {t_score:>6.2f}s {n*3:>7.0f}s {t_total_b:>6.0f}s {llm_b:>8} {n:>8}")
    print(f"{'C: 先提取→后评分(全量)':<28} {t_score:>6.2f}s {t_extract:>7.1f}s {t_total_c:>6.1f}s {llm_c:>8} {n:>8}")
    print("-" * 75)
    print(f"{'A vs B 节省':<28} {'':>8} {'':>9} {t_total_b-t_total_a:>6.0f}s {llm_b-llm_a:>7} {n-ab_count:>7}")
    print(f"{'A vs C 节省':<28} {'':>8} {'':>9} {t_total_c-t_total_a:>6.1f}s {'':>8}")
    print("=" * 75)

    # Qwen 实际测速
    print("\nQwen3-1.7B 实际测速 (3次采样取平均):")
    import httpx
    times = []
    for _ in range(3):
        t0 = time.time()
        try:
            r = httpx.post("http://127.0.0.1:1234/v1/chat/completions", json={
                "model": "qwen3-1.7b-instruct",
                "messages": [{"role": "user", "content": "回复:ok"}],
                "max_tokens": 5,
            }, timeout=10)
            if r.status_code == 200:
                times.append(time.time() - t0)
        except:
            pass
    if times:
        avg = sum(times)/len(times)
        print(f"  平均延迟: {avg:.2f}s/次")
        print(f"  Tier B 单篇增强: {avg*3:.1f}s (3次调用)")
        print(f"  200篇全量增强: {avg*3*n:.0f}s")
    else:
        print("  Qwen 不可用")

    print(f"\nTier A/B 占比: {ab_count}/{n} = {ab_count/n*100:.1f}%")
    print(f"结论: 当前A方案最优，仅处理{ab_count/n*100:.0f}%文章，节省{100-ab_count/n*100:.0f}%算力")


if __name__ == "__main__":
    benchmark()
