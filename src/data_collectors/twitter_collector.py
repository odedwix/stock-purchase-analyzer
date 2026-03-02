import asyncio
import logging
import re
from html import unescape
from typing import Any
from xml.etree import ElementTree

import httpx

from src.data_collectors.base import BaseCollector

logger = logging.getLogger(__name__)

# Nitter instances to try (public Twitter frontends with RSS support)
NITTER_INSTANCES = [
    "nitter.net",
    "nitter.privacydev.net",
    "nitter.poast.org",
]

# Influential finance / stock Twitter accounts to check
FINANCE_ACCOUNTS = [
    "unusual_whales",
    "DeItaone",
    "zaborsky_",
    "jimcramer",
    "carlaborsa1",
    "elikimon",
]

# Google search fallback user agent
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class TwitterCollector(BaseCollector):
    """Collects X/Twitter sentiment without API keys.

    Strategy (tried in order):
      1. Nitter RSS feeds – public Twitter mirrors that expose RSS.
      2. Google search fallback – ``site:twitter.com OR site:x.com`` scoped to
         the last 24 hours, parsed for tweet-like text.

    Because scraping Twitter is inherently fragile, every code path is wrapped
    in error handling and the collector always returns a valid (possibly empty)
    result dict.
    """

    def __init__(self) -> None:
        from config.settings import settings

        super().__init__(cache_ttl=settings.sentiment_cache_ttl)

    # ------------------------------------------------------------------
    # BaseCollector interface
    # ------------------------------------------------------------------

    async def _fetch_raw(self, symbol: str) -> Any:
        """Try Nitter RSS first, fall back to Google search scraping."""
        posts: list[str] = []

        # 1. Nitter search RSS ------------------------------------------
        nitter_posts = await self._fetch_nitter_search(symbol)
        posts.extend(nitter_posts)

        # 2. Nitter – influential finance accounts ----------------------
        account_posts = await self._fetch_nitter_accounts(symbol)
        posts.extend(account_posts)

        # 3. Fallback: Google search for tweets -------------------------
        if not posts:
            logger.info(
                "Nitter returned no results for %s; falling back to Google search",
                symbol,
            )
            google_posts = await self._fetch_google_tweets(symbol)
            posts.extend(google_posts)

        return posts

    def _transform(self, symbol: str, raw: Any) -> dict:
        """Keyword-based sentiment analysis mirroring RedditCollector."""
        posts: list[str] = raw

        if not posts:
            return {
                "posts": [],
                "mention_count": 0,
                "sentiment_summary": {
                    "bullish": 0,
                    "bearish": 0,
                    "neutral": 0,
                },
                "sentiment_score": 0.0,
            }

        bullish_words = {
            "buy", "bull", "bullish", "long", "calls", "moon", "rocket",
            "undervalued", "breakout", "support", "accumulate", "dip",
            "opportunity", "upside", "growth", "strong", "beat", "earnings",
            "upgrade", "outperform",
        }
        bearish_words = {
            "sell", "bear", "bearish", "short", "puts", "crash",
            "overvalued", "bubble", "resistance", "dump", "downgrade",
            "risk", "decline", "weak", "miss", "downside", "fear",
            "recession", "layoffs", "lawsuit",
        }

        bullish_count = 0
        bearish_count = 0
        neutral_count = 0

        for text in posts:
            lower = text.lower()
            bull_hits = sum(1 for w in bullish_words if w in lower)
            bear_hits = sum(1 for w in bearish_words if w in lower)

            if bull_hits > bear_hits:
                bullish_count += 1
            elif bear_hits > bull_hits:
                bearish_count += 1
            else:
                neutral_count += 1

        total_opinionated = bullish_count + bearish_count
        sentiment_score = 0.0
        if total_opinionated > 0:
            sentiment_score = (bullish_count - bearish_count) / total_opinionated

        return {
            "posts": posts[:50],  # cap stored posts at 50
            "mention_count": len(posts),
            "sentiment_summary": {
                "bullish": bullish_count,
                "bearish": bearish_count,
                "neutral": neutral_count,
            },
            "sentiment_score": round(sentiment_score, 3),
        }

    # ------------------------------------------------------------------
    # Nitter helpers
    # ------------------------------------------------------------------

    async def _fetch_nitter_search(self, symbol: str) -> list[str]:
        """Search Nitter RSS for tweets mentioning *symbol*."""
        posts: list[str] = []

        async with httpx.AsyncClient(
            timeout=12,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            for instance in NITTER_INSTANCES:
                if posts:
                    break  # already got results from a previous instance
                try:
                    url = f"https://{instance}/search/rss"
                    params = {"f": "tweets", "q": f"${symbol} stock"}
                    response = await client.get(url, params=params)

                    if response.status_code != 200:
                        logger.debug(
                            "Nitter %s returned %s", instance, response.status_code
                        )
                        continue

                    posts.extend(self._parse_rss(response.text))
                    if posts:
                        logger.info(
                            "Nitter %s returned %d posts for %s",
                            instance, len(posts), symbol,
                        )
                except Exception as e:
                    logger.debug("Nitter %s failed: %s", instance, e)

        return posts

    async def _fetch_nitter_accounts(self, symbol: str) -> list[str]:
        """Check influential finance accounts for mentions of *symbol*."""
        posts: list[str] = []
        working_instance: str | None = None

        async with httpx.AsyncClient(
            timeout=12,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            # Find a working Nitter instance first
            for instance in NITTER_INSTANCES:
                try:
                    probe = await client.get(
                        f"https://{instance}/{FINANCE_ACCOUNTS[0]}/rss"
                    )
                    if probe.status_code == 200:
                        working_instance = instance
                        # Parse the probe response too
                        account_posts = self._parse_rss(probe.text)
                        for text in account_posts:
                            if symbol.lower() in text.lower() or f"${symbol}".lower() in text.lower():
                                posts.append(text)
                        break
                except Exception:
                    continue

            if working_instance is None:
                return posts

            # Fetch remaining accounts
            for account in FINANCE_ACCOUNTS[1:]:
                try:
                    url = f"https://{working_instance}/{account}/rss"
                    response = await client.get(url)
                    if response.status_code != 200:
                        continue

                    account_posts = self._parse_rss(response.text)
                    for text in account_posts:
                        if symbol.lower() in text.lower() or f"${symbol}".lower() in text.lower():
                            posts.append(text)

                    # Be polite — small delay between requests
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.debug("Nitter account %s failed: %s", account, e)

        return posts

    @staticmethod
    def _parse_rss(xml_text: str) -> list[str]:
        """Extract tweet texts from an RSS XML document."""
        texts: list[str] = []
        try:
            root = ElementTree.fromstring(xml_text)
            # RSS items live under <channel><item>
            for item in root.iter("item"):
                title_el = item.find("title")
                desc_el = item.find("description")
                # Prefer description (full text); fall back to title
                raw = ""
                if desc_el is not None and desc_el.text:
                    raw = desc_el.text
                elif title_el is not None and title_el.text:
                    raw = title_el.text

                if raw:
                    clean = _strip_html(unescape(raw)).strip()
                    if clean:
                        texts.append(clean)
        except ElementTree.ParseError:
            pass
        return texts

    # ------------------------------------------------------------------
    # Google fallback
    # ------------------------------------------------------------------

    async def _fetch_google_tweets(self, symbol: str) -> list[str]:
        """Search Google for recent tweets about *symbol*."""
        posts: list[str] = []

        query = f"site:twitter.com OR site:x.com ${symbol} stock"
        url = "https://www.google.com/search"
        params = {
            "q": query,
            "tbs": "qdr:d",  # last 24 hours
            "num": 20,
        }

        try:
            async with httpx.AsyncClient(
                timeout=15,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
            ) as client:
                response = await client.get(url, params=params)

                if response.status_code != 200:
                    logger.debug("Google search returned %s", response.status_code)
                    return posts

                posts = self._parse_google_results(response.text, symbol)
                logger.info(
                    "Google search returned %d tweet-like results for %s",
                    len(posts), symbol,
                )
        except Exception as e:
            logger.debug("Google tweet search failed: %s", e)

        return posts

    @staticmethod
    def _parse_google_results(html: str, symbol: str) -> list[str]:
        """Extract tweet-like text snippets from Google search result HTML.

        This is intentionally simple — Google's HTML structure changes often,
        so we grab visible text snippets that look tweet-sized.
        """
        texts: list[str] = []

        # Google wraps snippets in various <span> and <div> elements.
        # We look for text chunks between tags that are long enough to be
        # tweet snippets and contain the symbol.
        snippet_pattern = re.compile(r">([^<]{40,280})<", re.DOTALL)
        symbol_lower = symbol.lower()

        for match in snippet_pattern.finditer(html):
            text = unescape(match.group(1)).strip()
            # Keep only snippets that reference the symbol
            if symbol_lower in text.lower() or f"${symbol_lower}" in text.lower():
                # Skip navigational / UI text
                if any(skip in text.lower() for skip in [
                    "sign in", "privacy", "terms", "cookie", "javascript",
                    "before you continue", "did you mean",
                ]):
                    continue
                texts.append(text)

        # De-duplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for t in texts:
            if t not in seen:
                seen.add(t)
                unique.append(t)

        return unique[:30]


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    return _HTML_TAG_RE.sub("", text)
