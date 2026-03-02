import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import quote

import httpx

from src.data_collectors.base import BaseCollector
from src.models.stock_data import NewsItem

logger = logging.getLogger(__name__)

# Google News RSS base URLs
_GOOGLE_NEWS_TOP = (
    "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
)
_GOOGLE_NEWS_BUSINESS = (
    "https://news.google.com/rss/topics/"
    "CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB"
    "?hl=en-US&gl=US&ceid=US:en"
)
_GOOGLE_NEWS_SEARCH = (
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
)

# Search terms that capture broad geopolitical and macro-economic events
SEARCH_TERMS = [
    "stock market",
    "geopolitics",
    "war",
    "tariffs",
    "federal reserve",
    "inflation",
    "oil prices",
    "trade war",
    "sanctions",
]

# Polite delay between RSS requests to avoid being blocked
_REQUEST_DELAY_SECONDS = 0.5

# Maximum articles to keep per individual feed
_MAX_PER_FEED = 15


class WorldNewsCollector(BaseCollector):
    """Collects general world news from Google News RSS feeds.

    Unlike the stock-specific NewsCollector (which uses finvizfinance), this
    collector fetches broad geopolitical, macroeconomic, and world news that
    may affect the markets but would not appear in a single-ticker news feed.

    No API key is required -- all data comes from public Google News RSS.
    """

    def __init__(self) -> None:
        from config.settings import settings

        super().__init__(cache_ttl=settings.news_cache_ttl)

    # ------------------------------------------------------------------
    # BaseCollector interface
    # ------------------------------------------------------------------

    async def _fetch_raw(self, symbol: str) -> Any:
        """Fetch RSS feeds in parallel batches, return raw article dicts.

        *symbol* is accepted for interface compatibility but is not used for
        the top-level and business feeds.  It IS appended as an extra search
        term so that the results are also enriched with news mentioning the
        specific ticker when available.
        """
        feed_urls = self._build_feed_urls(symbol)
        all_articles: list[dict] = []

        async with httpx.AsyncClient(
            timeout=20,
            headers={"User-Agent": "StockAnalyzer/0.1 (educational project)"},
            follow_redirects=True,
        ) as client:
            for url in feed_urls:
                try:
                    response = await client.get(url)
                    if response.status_code != 200:
                        logger.warning(
                            "Google News RSS returned %s for %s",
                            response.status_code,
                            url[:120],
                        )
                        continue

                    articles = self._parse_rss(response.text)
                    all_articles.extend(articles[:_MAX_PER_FEED])
                except Exception as e:
                    # One feed failure must not abort the rest
                    logger.warning("RSS fetch failed for %s: %s", url[:120], e)

                # Be polite between requests
                await asyncio.sleep(_REQUEST_DELAY_SECONDS)

        return all_articles

    def _transform(self, symbol: str, raw: Any) -> list[NewsItem]:
        """De-duplicate by title and convert to ``NewsItem`` objects."""
        seen_titles: set[str] = set()
        items: list[NewsItem] = []

        for article in raw:
            title = article.get("title", "").strip()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)

            items.append(
                NewsItem(
                    title=title,
                    source=article.get("source", ""),
                    url=article.get("url", ""),
                    published_at=article.get("published_at", ""),
                    snippet=article.get("snippet", ""),
                )
            )

        logger.info(
            "WorldNewsCollector: %d unique articles after de-duplication", len(items)
        )
        return items

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_feed_urls(symbol: str) -> list[str]:
        """Return the ordered list of RSS URLs to fetch."""
        urls = [
            _GOOGLE_NEWS_TOP,
            _GOOGLE_NEWS_BUSINESS,
        ]
        for term in SEARCH_TERMS:
            urls.append(_GOOGLE_NEWS_SEARCH.format(query=quote(term)))

        # Also search for the specific stock symbol if provided
        if symbol:
            urls.append(
                _GOOGLE_NEWS_SEARCH.format(query=quote(f"{symbol} stock"))
            )

        return urls

    @staticmethod
    def _parse_rss(xml_text: str) -> list[dict]:
        """Parse an RSS 2.0 XML document and return a list of article dicts."""
        articles: list[dict] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning("RSS XML parse error: %s", e)
            return articles

        # RSS 2.0: <rss><channel><item>...</item></channel></rss>
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pub_date_el = item.find("pubDate")
            source_el = item.find("source")
            description_el = item.find("description")

            title = unescape(title_el.text.strip()) if title_el is not None and title_el.text else ""
            url = link_el.text.strip() if link_el is not None and link_el.text else ""
            published_at = pub_date_el.text.strip() if pub_date_el is not None and pub_date_el.text else ""
            source = source_el.text.strip() if source_el is not None and source_el.text else ""
            snippet = ""
            if description_el is not None and description_el.text:
                # Google News descriptions are often HTML fragments; strip tags
                snippet = _strip_html_tags(unescape(description_el.text))[:300]

            if title:
                articles.append({
                    "title": title,
                    "source": source,
                    "url": url,
                    "published_at": published_at,
                    "snippet": snippet,
                })

        return articles


def _strip_html_tags(html: str) -> str:
    """Remove HTML tags from a string, returning plain text."""
    import re

    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text
