"""
config/settings.py — Centralized, configurable thresholds for the cascade engine.

Previously hardcoded in cascade.py (MIN_CONTENT_LEN=200, etc.),
now pulled into one place with domain-specific overrides.

Usage:
    from config.settings import get_settings
    s = get_settings()
    print(s.min_content_len)          # 200
    print(s.min_content_len_for("wsj.com"))  # 200 (default) or domain override
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CascadeSettings:
    """Global + per-domain cascade settings with sensible defaults."""

    # ── Global defaults ────────────────────────────────────────────
    min_content_len: int = 200          # Below this → treat as "blocked/empty"
    direct_timeout: float = 30.0        # HTTP timeout for direct fetches (seconds)
    archive_timeout: float = 30.0
    scrapling_timeout: float = 45.0     # TLS fingerprinting takes longer
    browser_timeout: float = 60.0       # Playwright launch + networkidle

    # Rate limiting
    rate_limit_default_delay: float = 1.0   # seconds between requests (same domain)
    rate_limit_browser_delay: float = 5.0   # extra cooldown for browser strategy

    # LLM extraction
    llm_max_input_chars: int = 8000     # truncate content before sending to LLM
    llm_model: str = "deepseek-chat"
    llm_api_base: str = "https://api.deepseek.com/v1"

    # Batch scraping
    batch_max_workers: int = 4          # ThreadPoolExecutor workers
    batch_retry_attempts: int = 2       # retry failed URLs N times

    # ── Per-domain overrides ───────────────────────────────────────
    # Some sites return shorter valid content (e.g., live blog cards)
    domain_min_content_len: dict = field(default_factory=lambda: {
        # WSJ live blog cards can be short
        # "wsj.com": 100,
    })

    domain_timeout: dict = field(default_factory=lambda: {
        # Slow sites need longer timeouts
        # "bloomberg.com": 45.0,
    })

    domain_rate_delay: dict = field(default_factory=lambda: {
        # Friendly sites can be faster
        "reuters.com": 0.5,
        "apnews.com": 0.5,
        "bbc.com": 0.5,
        "aljazeera.com": 0.5,
    })

    # ── Methods ────────────────────────────────────────────────────

    def min_content_len_for(self, domain: str) -> int:
        """Get min_content_len for a domain, falling back to global default."""
        for d, val in self.domain_min_content_len.items():
            if d in domain:
                return val
        return self.min_content_len

    def timeout_for(self, domain: str, strategy: str) -> float:
        """Get timeout for a domain+strategy combo."""
        base = {
            "direct": self.direct_timeout,
            "archive": self.archive_timeout,
            "scrapling": self.scrapling_timeout,
            "browser": self.browser_timeout,
        }.get(strategy, 30.0)

        for d, val in self.domain_timeout.items():
            if d in domain:
                return val
        return base

    def rate_delay_for(self, domain: str) -> float:
        """Get rate limit delay for a domain."""
        for d, val in self.domain_rate_delay.items():
            if d in domain:
                return val
        return self.rate_limit_default_delay


# Singleton
_settings: Optional[CascadeSettings] = None


def get_settings() -> CascadeSettings:
    global _settings
    if _settings is None:
        _settings = CascadeSettings()
    return _settings


def update_settings(**kwargs):
    """Update global settings at runtime (e.g., from CLI args)."""
    global _settings
    s = get_settings()
    for k, v in kwargs.items():
        if hasattr(s, k):
            setattr(s, k, v)
