"""
news_intel/router.py — Intelligence Router

根据 News Value Score 将文章分流到三个增强层级：

  Tier C (<60) : enhance_python()  — 零成本，规则抽取
  Tier B (60-90): enhance_qwen()    — Qwen3-1.7B 本地免费增强
  Tier A (>90) : enhance_deepseek() — DeepSeek V4 Flash 深度分析
"""

from .enhancers import enhance_python, enhance_qwen, enhance_deepseek


def route(
    title: str,
    description: str,
    scores: dict,
    content_md: str = "",
) -> dict:
    """
    根据评分路由到对应增强层级。

    Args:
        title: RSS标题
        description: RSS摘要
        scores: scorer.score_article() 的输出 {total, tier, entities, categories, ...}
        content_md: 正文 Markdown（Tier A 需要）

    Returns:
        {tags, entities, summary_cn, summary_en, method, llm_model, llm_cost,
         ...(Tier A 额外字段: event, impact, market_signal, risk_level, ...)}
    """
    tier = scores.get("tier", "C")
    entities = scores.get("entities", {})
    categories = scores.get("categories", [])

    if tier == "A":
        return enhance_deepseek(
            title=title,
            description=description,
            content_md=content_md,
            scores=scores,
            entities=entities,
        )
    elif tier == "B":
        return enhance_qwen(
            title=title,
            description=description,
            content_md=content_md,
            entities=entities,
            categories=categories,
        )
    else:  # Tier C
        return enhance_python(
            title=title,
            description=description,
            content_md=content_md,
            entities=entities,
            categories=categories,
        )
