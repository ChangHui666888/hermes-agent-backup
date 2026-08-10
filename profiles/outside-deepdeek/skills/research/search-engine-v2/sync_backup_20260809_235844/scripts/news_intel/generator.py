"""
news_intel/generator.py v4.4 - Event-Level Intelligence Generator

Event Dossier -> DeepSeek/Qwen -> Event Intelligence
(new v4.4: enhanced prompt using evidence, source_chain, timeline)
"""
import json, os, time, logging, re
import httpx

logger = logging.getLogger(__name__)

QWEN_BASE = "http://127.0.0.1:1234/v1"
DEEPSEEK_BASE = "https://api.deepseek.com/v1"

# v4.4 Event-Level Prompt: extracts meaning, not just summary
EVENT_INTEL_PROMPT = """You are a senior geopolitical/market intelligence analyst.

Analyze the following Event Dossier and produce structured intelligence:

{event_dossier}

Output ONLY valid JSON:
{{
  "event_summary": "One-sentence event summary (50 chars max)",
  "significance": "Why this matters: strategic significance assessment (80 chars max)",
  "impact": {{
    "geopolitical": "escalation|deescalation|neutral|mixed",
    "market": "bullish|bearish|neutral|uncertain",
    "industry": ["sectors affected"]
  }},
  "risk_level": "low|medium|high|critical",
  "forecast": "Most likely next development (60 chars max)",
  "key_uncertainty": "Biggest unknown / what to watch (60 chars max)",
  "entities_affected": ["entity names"],
  "confidence": 0.0-1.0
}}"""


def _format_event_dossier(ev: dict) -> str:
    """Format v4.4 event object into a readable dossier for LLM."""
    parts = []
    parts.append(f"Event: {ev.get('title', '')}")
    parts.append(f"Type: {ev.get('event_type', '')} | Stage: {ev.get('stage', '')}")
    parts.append(f"Confidence: {ev.get('confidence', 0):.2f} | Articles: {ev.get('article_count', 0)}")

    s = ev.get("subject", {})
    a = ev.get("action", {})
    o = ev.get("object", {})
    if isinstance(s, dict) and s.get("name"):
        parts.append(f"Subject: {s['name']} ({s.get('type', '')})")
    if isinstance(a, dict) and a.get("type"):
        parts.append(f"Action: {a['type']} - {a.get('detail', '')}")
    if isinstance(o, dict) and o.get("name"):
        parts.append(f"Object: {o['name']} ({o.get('type', '')})")

    evidence = ev.get("evidence", [])
    if evidence:
        parts.append("Evidence:")
        for eq in evidence[:3]:
            parts.append(f"  - [{eq.get('source', '')}] {eq.get('quote', '')[:120]}")

    timeline = ev.get("timeline", [])
    if timeline:
        parts.append("Timeline:")
        for t in timeline:
            parts.append(f"  {t.get('time', '')}: {t.get('update', '')} ({t.get('source', '')})")

    chain = ev.get("source_chain", [])
    if chain:
        parts.append("Sources:")
        for sc in chain[:5]:
            role = "BREAK" if sc.get("role") == "break" else "FOLLOW"
            parts.append(f"  [{role}] {sc.get('source_name', '')}")

    return "\n".join(parts)


def generate_intel(ev: dict, force_deepseek: bool = False) -> dict | None:
    """Generate event-level intelligence analysis.

    v4.4: Uses full event dossier (evidence + timeline + source_chain)
    instead of just title+entities.
    """
    dossier = _format_event_dossier(ev)
    prompt = EVENT_INTEL_PROMPT.format(event_dossier=dossier[:3000])

    if force_deepseek:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            logger.warning("[generator] No DEEPSEEK_API_KEY")
            return None
        return _call_deepseek(prompt, api_key)

    return _call_qwen(prompt)


# ---- Backward compat wrappers -----------------------------------

INSIGHT_PROMPT = """You are an international news analyst. Based on the following event timeline, generate insight analysis.

Requirements:
1. Do not add facts not present
2. Distinguish facts from speculation
3. Mark impact scope (market/geopolitical/industry)

Output JSON:
{{
  "summary": "One-sentence event summary (50 chars)",
  "timeline": "Key time points (50 chars)",
  "key_drivers": "Key driving factors (50 chars)",
  "impact": "Direct impact on market/industry/geopolitics (100 chars)",
  "market_effect": "bullish|bearish|neutral",
  "geopolitical_effect": "escalation|deescalation|neutral",
  "uncertainty": "low|medium|high",
  "confidence": 0.0-1.0
}}

Event title: {title}
Related entities: {entities}
Article count: {count}
"""


def generate_insight(event: dict, force_deepseek: bool = False) -> dict | None:
    """Backward compat: simple insight from title+entities."""
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


def generate_for_event(event: dict) -> dict | None:
    """v4.4: Route to event-level intelligence if dossier is complete."""
    if event.get("evidence") or event.get("source_chain"):
        return generate_intel(event, force_deepseek=True)
    tier = event.get("tier") or ("A" if event.get("impact_level") == "HIGH" else "B")
    return generate_insight(event, force_deepseek=(tier == "A"))


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
    try:
        m = re.search(r"\{[\s\S]*\}", raw)
        return json.loads(m.group(0)) if m else json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
