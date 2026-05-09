"""
Web search tool using DuckDuckGo (no API key required).

Returns a list of dicts with 'title', 'url', and 'snippet' fields.
Never raises — returns a single error entry instead so the pipeline can continue.
"""

import logging

try:
    from ddgs import DDGS                  # ddgs >= 1.0 (new package name)
except ImportError:
    from duckduckgo_search import DDGS     # duckduckgo-search < 7 (legacy)

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """
    Search DuckDuckGo for *query* and return up to *max_results* results.

    Each result is {'title': str, 'url': str, 'snippet': str}.
    On any failure returns [{'title': 'Search failed', 'url': '', 'snippet': <error>}].
    """
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in raw
        ]
        logger.info("Web search '%s' → %d results", query, len(results))
        return results
    except Exception as exc:
        logger.warning("Web search failed for '%s': %s", query, exc)
        return [{"title": "Search failed", "url": "", "snippet": str(exc)}]
