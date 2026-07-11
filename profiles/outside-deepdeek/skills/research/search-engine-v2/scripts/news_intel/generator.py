"""
news_intel/generator.py — L9 洞察生成器

事件 → DeepSeek/Qwen → Insight
"""
import json, os, time, logging
import httpx

logger = logging.getLogger(__name__)

QWEN_BASE = "http://127.0.0.1:1234/v1"
DEEPSEEK_BASE = "https://api.deepseek.com/v1"

INSIGHT_PROMPT = """分析以下事件，输出JSON:
{{
  "summary": "事件一句话概述(50字)",
  "impact_analysis": "对市场/行业/地缘的直接影响(100字)",
  "drivers": "关键驱动因素(50字)",
  "sentiment": "positive/neutral/negative",
  "confidence": 0.0-1.0
}}

事件标题: {title}
涉及实体: {entities}
关联文章数: {count}
"""


def generate_insight(event: dict, force_deepseek: bool = False) -> dict | None:
    """
    为事件生成洞察。
    - 默认用 Qwen3 本地（免费）
    - force_deepseek=True 时用 DeepSeek V4 Flash
    """
    prompt = INSIGHT_PROMPT.format(
        title=event.get("title", ""),
        entities=", ".join(event.get("entities", [])[:10]),
        count=event.get("article_count", 0),
    )

    if force_deepseek:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            logger.warning("[generator] No DEEPSEEK_API_KEY, falling back to Qwen")
        else:
            return _call_deepseek(prompt, api_key)

    return _call_qwen(prompt)


def _call_qwen(prompt: str) -> dict | None:
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{QWEN_BASE}/chat/completions", json={
                "model": "qwen3-1.7b-instruct",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
            })
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            return _parse_json(raw)
    except Exception as e:
        logger.warning(f"[generator] Qwen error: {e}")
        return None


def _call_deepseek(prompt: str, api_key: str) -> dict | None:
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{DEEPSEEK_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "deepseek-v4-flash",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 500,
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            return _parse_json(raw)
    except Exception as e:
        logger.warning(f"[generator] DeepSeek error: {e}")
        return None


def _parse_json(raw: str) -> dict | None:
    import re
    try:
        m = re.search(r"\{[\s\S]*\}", raw)
        return json.loads(m.group(0)) if m else json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def generate_for_event(event: dict) -> dict | None:
    """自动路由：Tier A → DeepSeek, 其余 → Qwen3"""
    tier = event.get("tier") or ("A" if event.get("impact_level") == "HIGH" else "B")
    return generate_insight(event, force_deepseek=(tier == "A"))
