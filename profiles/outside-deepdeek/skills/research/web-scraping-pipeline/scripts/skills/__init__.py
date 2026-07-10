"""Web scraping skills package"""
from .base import BaseSkill, SkillResult, extract_years, now
from .s01_direct_extract import DirectPageExtractSkill
from .s02_search_pick_extract import SearchPickExtractSkill
from .s03_multi_url_candidate import MultiUrlCandidateSkill
from .s04_structured_news import StructuredNewsExtractionSkill
from .s05_live_blog_cards import LiveBlogCardExtractionSkill
from .s06_temporal_validation import TemporalValidationSkill
from .s07_js_render import JSRenderCrawlSkill
from .s08_archive_fallback import ArchiveFallbackSkill
from .s09_multi_source_merge import MultiSourceMergeSkill
from .s10_entity_driven import EntityDrivenExtractionSkill

__all__ = [
    "BaseSkill", "SkillResult", "extract_years", "now",
    "DirectPageExtractSkill", "SearchPickExtractSkill", "MultiUrlCandidateSkill",
    "StructuredNewsExtractionSkill", "LiveBlogCardExtractionSkill",
    "TemporalValidationSkill", "JSRenderCrawlSkill", "ArchiveFallbackSkill",
    "MultiSourceMergeSkill", "EntityDrivenExtractionSkill",
]
