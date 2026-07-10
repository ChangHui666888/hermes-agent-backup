"""pusher.py — Hermes → FastAPI 批量推送"""
import json, os, logging
import httpx

logger = logging.getLogger(__name__)
API_BASE = os.environ.get("NEWS_API_BASE", "http://localhost:8000")
INTERNAL_TOKEN = os.environ.get("NEWS_API_TOKEN", "hermes-pipeline-secret-2026")


def push_batch(articles: list[dict], api_base: str = None) -> dict:
    """批量推送。一次 HTTP 请求发送全部文章。"""
    base = api_base or API_BASE
    if not articles:
        return {"ok": 0, "fail": 0}

    body = []
    for a in articles:
        s = a.get("structured", {})
        sc = a.get("scores", {})
        item = {
            "url": a.get("url", ""),
            "title": s.get("headline") or a.get("title", ""),
            "content_md": a.get("content", ""),
            "published_at": s.get("published_at"),
            "source_name": a.get("source_name") or a.get("domain", ""),
            "source_domain": a.get("domain", ""),
            "category": sc.get("categories", [None])[0] if "categories" in sc else None,
            "tags": s.get("tags") or sc.get("categories", []),
            "entities": sc.get("entities") or s.get("entities", {}),
            "score_total": sc.get("total", 0) if isinstance(sc, dict) else 0,
            "score_breakdown": sc if isinstance(sc, dict) else {},
            "tier": sc.get("tier") if isinstance(sc, dict) else None,
            "analysis": a.get("analysis", {}),
            "summary_cn": s.get("summary_cn", ""),
            "summary": s.get("summary", ""),
            "key_points": s.get("key_points", []),
            "extraction_method": s.get("method") or s.get("_extraction_method"),
            "fetch_strategy": a.get("strategy_used"),
            "fetch_cost": a.get("total_cost", 0),
        }
        body.append({k: v for k, v in item.items() if v is not None})

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{base}/internal/news/batch",
                json=body,
                headers={"X-Internal-Token": INTERNAL_TOKEN},
            )
            if resp.status_code == 200:
                result = resp.json()
                return {"ok": result.get("ok", len(body)), "fail": result.get("fail", 0)}
            logger.warning(f"[pusher] batch {resp.status_code}: {resp.text[:100]}")
            return {"ok": 0, "fail": len(body)}
    except Exception as e:
        logger.warning(f"[pusher] batch error: {e}")
        return {"ok": 0, "fail": len(body)}


def push_article(article: dict, api_base: str = None, token: str = None) -> bool:
    """单篇推送（保留兼容）"""
    result = push_batch([article], api_base)
    return result["ok"] > 0
