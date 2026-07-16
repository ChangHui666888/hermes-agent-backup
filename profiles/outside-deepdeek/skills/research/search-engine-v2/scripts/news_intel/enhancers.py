"""
news_intel/enhancers.py — 三层智能增强

  Tier C (<60) : Python-only — 规则抽取（零成本）
  Tier B (60-90): Qwen3-1.7B 本地 — 标签 + 实体 + 短摘要
  Tier A (>90) : DeepSeek V4 Flash — 深度分析（事件/影响/市场信号/风险）
"""

import json
import os
import re
import time
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Tier C: Python-only ────────────────────────────────────────

def enhance_python(title: str, description: str, content_md: str = "",
                   entities: dict = None, categories: list = None) -> dict:
    """
    零 LLM 增强：规则推导标签 + 实体 + 分类。

    Returns: {tags, entities, summary_cn, summary_en, category}
    """
    text = f"{title} {description}"
    tags = _derive_tags(text, entities, categories)
    all_entities = _merge_entities(entities or {}, text)
    summary_cn = _rule_summary_cn(description or title, max_chars=100)
    summary_en = _rule_summary_en(description or title, max_chars=100)
    category = (categories or ["general"])[0] if categories else "general"

    return {
        "tags": tags,
        "entities": all_entities,
        "summary_cn": summary_cn,
        "summary_en": summary_en,
        "category": category,
        "method": "python",
        "llm_model": None,
        "llm_cost": 0.0,
    }


def _derive_tags(text: str, entities: dict = None, categories: list = None) -> list[str]:
    """从文本推导标签"""
    tags = set()
    tag_map = {
        # 金融
        "利率": "利率", "降息": "降息", "加息": "加息", "Fed": "美联储",
        "央行": "央行", "通胀": "通胀", "CPI": "CPI",
        "财报": "财报", "earnings": "财报",
        "石油": "石油", "油价": "石油", "oil": "石油",
        "黄金": "黄金", "gold": "黄金",
        "暴跌": "暴跌", "暴涨": "暴涨",
        # AI
        "AI": "AI", "GPT": "AI", "OpenAI": "AI", "Gemini": "AI",
        "模型": "AI", "GPU": "半导体", "芯片": "半导体",
        # 地缘
        "战争": "地缘", "停火": "地缘", "ceasefire": "地缘",
        "制裁": "制裁", "关税": "关税",
        # 实体
        "Trump": "特朗普", "特朗普": "特朗普",
        "NVIDIA": "NVIDIA", "Tesla": "Tesla",
        "伊朗": "伊朗", "Iran": "伊朗",
        "中国": "中国", "China": "中国",
    }
    lower = text.lower()
    for kw, tag in tag_map.items():
        if kw.lower() in lower:
            tags.add(tag)
    if categories:
        tags.update(c[:8] for c in categories[:3])
    return list(tags)[:10]


def _merge_entities(entities: dict, text: str) -> dict:
    """合并配置实体 + 文本正则提取"""
    result = {"companies": list(entities.get("companies", [])),
              "persons": list(entities.get("persons", [])),
              "countries": list(entities.get("countries", []))}
    # 简单正则补提公司名（$STOCK 模式）
    tickers = re.findall(r"\b[A-Z]{2,5}\b", text)
    known_tickers = {"NVDA": "NVIDIA", "TSLA": "Tesla", "AAPL": "Apple",
                     "MSFT": "Microsoft", "GOOGL": "Google", "META": "Meta",
                     "AMD": "AMD", "INTC": "Intel"}
    for t in tickers:
        if t in known_tickers and known_tickers[t] not in result["companies"]:
            result["companies"].append(known_tickers[t])
    return result


def _rule_summary_cn(text: str, max_chars: int = 100) -> str:
    """中文摘要：取前2句"""
    sents = re.split(r"[。！？\n]", text)
    parts = [s.strip() for s in sents if len(s.strip()) > 5]
    summary = "。".join(parts[:2])
    return summary[:max_chars] + ("。" if len(summary) > max_chars and not summary.endswith("。") else "")


def _rule_summary_en(text: str, max_chars: int = 100) -> str:
    """英文摘要：取前2句"""
    sents = re.split(r"(?<=[.!?])\s+", text)
    parts = [s.strip() for s in sents if len(s.strip()) > 10]
    summary = ". ".join(parts[:2])
    return summary[:max_chars]


# ── Tier B: Qwen3-1.7B 本地 ────────────────────────────────────

QWEN_BASE = "http://127.0.0.1:1234/v1"
QWEN_MODEL = "qwen3-1.7b-instruct"
_qwen_available = True  # 全局标记：第一次失败后跳过所有后续调用
_qwen_lock = __import__("threading").Lock()  # 并发安全

TAG_PROMPT = """你是一个新闻标签系统。给定标题和摘要，输出 5-8 个标签（中英文混合）。
只输出 JSON 数组，不要其他内容。
示例: ["AI","NVIDIA","芯片","出口管制","半导体"]"""

ENTITY_PROMPT = """从以下新闻中提取实体。只输出 JSON:
{"companies":["公司名"],"persons":["人名"],"countries":["国家"]}"""

SUMMARY_PROMPT = """用中文一句话总结以下新闻（30字以内）。只输出这句话。"""


def _call_qwen(prompt: str, user_text: str, max_tokens: int = 200) -> str | None:
    """调用本地 LM Studio Qwen3-1.7B，60秒超时。首次失败后全局跳过。线程安全。"""
    global _qwen_available
    with _qwen_lock:
        if not _qwen_available:
            return None
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{QWEN_BASE}/chat/completions",
                json={
                    "model": QWEN_MODEL,
                    "messages": [
                        {"role": "user", "content": f"{prompt}\n\n{user_text}"},
                    ],
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        with _qwen_lock:
            _qwen_available = False
        logger.warning(f"[qwen] unavailable, skipping all: {e}")
        return None


QMERGE_PROMPT = """分析以下新闻，只输出JSON:
{
  "tags": ["标签1", "标签2"],
  "companies": ["公司名"],
  "persons": ["人名"],
  "countries": ["国家"],
  "organizations": ["组织名"],
  "actions": ["动作关键词"],
  "summary_cn": "20字以内中文摘要",
  "event_hint": "事件类型提示(如: 诉讼/谈判/军事冲突/财报/政策/科技发布)",
  "tone": -5.0
}
tone字段: 正面/合作=正值(0~10), 负面/冲突=负值(-10~0), 中性=0. 例如: 战争=-8, 和平协议=+7, 财报中性=0"""


def enhance_qwen(title: str, description: str, content_md: str = "",
                 entities: dict = None, categories: list = None) -> dict:
    """
    V4.2: Qwen3-1.7B 增强 — 标签 + 实体(含countries/organizations) + 动作 + 事件提示
    """
    text = f"标题: {title}\n摘要: {description}"[:600]

    raw = _call_qwen(QMERGE_PROMPT, text, max_tokens=500)
    data = _parse_json_dict(raw) or {}

    tags = data.get("tags") or _derive_tags(title + description, entities, categories)
    if isinstance(tags, str): tags = [tags]

    merged = _merge_entities(entities or {}, title + description)
    for key in ("companies", "persons", "countries", "organizations"):
        merged.setdefault(key, [])
        for item in (data.get(key) or []):
            if item not in merged[key]: merged[key].append(item)

    actions = data.get("actions", [])
    event_hint = data.get("event_hint", "")
    summary = data.get("summary_cn", "")

    return {
        "tags": tags,
        "entities": merged,
        "actions": actions if isinstance(actions, list) else [],
        "event_hint": event_hint,
        "summary_cn": (summary or _rule_summary_cn(description or title))[:100],
        "summary_en": _rule_summary_en(description or title),
        "category": (categories or ["general"])[0] if categories else "general",
        "method": "qwen3",
        "llm_model": QWEN_MODEL,
        "llm_cost": 0.0,
    }


def _parse_json_array(raw: str | None) -> list | None:
    if not raw:
        return None
    try:
        m = re.search(r"\[[\s\S]*\]", raw)
        return json.loads(m.group(0)) if m else json.loads(raw)
    except json.JSONDecodeError:
        return None


def _parse_json_dict(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        m = re.search(r"\{[\s\S]*\}", raw)
        return json.loads(m.group(0)) if m else json.loads(raw)
    except json.JSONDecodeError:
        return None


# ── Tier A: DeepSeek V4 Flash ───────────────────────────────────

DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-v4-flash"

ANALYSIS_PROMPT = """你是高级新闻分析编辑。分析以下新闻，输出 JSON:

{
  "event": "事件一句话概括",
  "impact": "对市场/行业/地缘的直接影响（50字以内）",
  "companies": ["受影响的上市公司"],
  "assets": ["受影响的资产：股票代码/商品/指数"],
  "market_signal": "bullish|bearish|neutral|uncertain",
  "risk_level": "low|medium|high|critical",
  "future_watch": "未来需要关注的关键节点（50字以内）",
  "confidence": 0.0-1.0
}"""


def enhance_deepseek(title: str, description: str, content_md: str = "",
                     scores: dict = None, entities: dict = None) -> dict:
    """
    DeepSeek V4 Flash 深度分析。仅对 >90 分文章触发。

    Returns: {event, impact, companies, assets, market_signal,
              risk_level, future_watch, confidence, tags, entities,
              summary_cn, summary_en, method, llm_model, llm_cost}
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("[deepseek] No DEEPSEEK_API_KEY")
        # 降级到 Python 规则
        return enhance_python(title, description, content_md, entities)

    # 压缩正文：取前 3000 字符的关键段落
    text = f"标题: {title}\n\n"
    if description:
        text += f"摘要: {description}\n\n"
    if content_md:
        # 取前 N 段
        paras = [p.strip() for p in content_md.split("\n\n") if len(p.strip()) > 30]
        text += "\n\n".join(paras[:8])  # 前8段
    text = text[:3000]

    start = time.monotonic()
    try:
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(
                f"{DEEPSEEK_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": ANALYSIS_PROMPT},
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 800,
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"[deepseek] API error: {e}")
        return enhance_python(title, description, content_md, entities)

    elapsed = time.monotonic() - start
    data = _parse_json_dict(raw) or {}

    # 合并基础信息
    tags = _derive_tags(title + description, entities)
    merged_entities = _merge_entities(entities or {}, title + description)
    if isinstance(data.get("companies"), list):
        for c in data["companies"]:
            if c not in merged_entities.get("companies", []):
                merged_entities.setdefault("companies", []).append(c)

    return {
        "event": data.get("event", ""),
        "impact": data.get("impact", ""),
        "companies": data.get("companies", []),
        "assets": data.get("assets", []),
        "market_signal": data.get("market_signal", "neutral"),
        "risk_level": data.get("risk_level", "low"),
        "future_watch": data.get("future_watch", ""),
        "confidence": data.get("confidence", 0.7),
        "tags": tags,
        "entities": merged_entities,
        "summary_cn": data.get("event", "") or _rule_summary_cn(description or title),
        "summary_en": _rule_summary_en(description or title),
        "category": "analysis",
        "method": "deepseek-flash",
        "llm_model": DEEPSEEK_MODEL,
        "llm_cost": round(elapsed * 0.0001, 6),  # 粗略估算
    }
