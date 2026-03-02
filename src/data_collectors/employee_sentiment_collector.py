"""Employee sentiment collector — what do employees say about the company?

Searches Reddit (career subreddits) and Google News RSS for employee
perspectives on company culture, management quality, layoffs, innovation, etc.
Filters for relevance to ensure posts actually discuss the target company.
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from html import unescape
from typing import Any
from urllib.parse import quote

import httpx
import yfinance as yf

from src.data_collectors.base import BaseCollector
from src.models.stock_data import NewsItem

logger = logging.getLogger(__name__)

# Subreddits where employees discuss companies
EMPLOYEE_SUBREDDITS = [
    "cscareerquestions",
    "experienceddevs",
    "jobs",
    "careerguidance",
    "antiwork",
    "technology",
]

# Google News RSS search template
_GOOGLE_NEWS_SEARCH = (
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
)

# News search queries (company name gets inserted)
_NEWS_SEARCH_TEMPLATES = [
    '"{company}" employees',
    '"{company}" workplace culture',
    '"{company}" layoffs OR hiring',
    '"{company}" management CEO',
    '"{company}" glassdoor OR reviews',
    '"{company}" glassdoor rating',
    '"{company}" employee satisfaction OR morale',
    '"{company}" layoffs 2024 OR 2025 OR 2026',
    '"{company}" return to office OR remote work policy',
]

# Theme detection keywords
_THEME_KEYWORDS = {
    "layoffs": ["layoff", "laid off", "firing", "rif", "restructur", "downsiz", "cut jobs", "job cuts"],
    "hiring_growth": ["hiring", "growing", "expansion", "new hires", "hiring spree", "headcount"],
    "poor_management": ["bad management", "terrible leadership", "incompetent", "toxic", "micromanag", "bureaucra", "dysfunction"],
    "good_management": ["great leadership", "good management", "well managed", "strong leadership", "visionary"],
    "innovation": ["innovative", "cutting edge", "r&d", "breakthrough", "pioneering", "ai ", "machine learning"],
    "stagnation": ["stagnant", "outdated", "legacy", "slow", "behind", "falling behind", "dinosaur"],
    "good_culture": ["great culture", "love working", "amazing team", "work-life balance", "benefits", "perks"],
    "bad_culture": ["toxic culture", "burnout", "overwork", "crunch", "terrible culture", "hostile"],
    "compensation": ["pay", "salary", "compensation", "stock options", "rsu", "bonus", "underpaid", "overpaid"],
    "product_quality": ["quality", "product", "customers love", "customer complaints", "buggy", "technical debt"],
}

# Employee-related keywords for relevance scoring
_EMPLOYEE_KEYWORDS = [
    "work at", "working at", "employee", "engineer at", "team at",
    "interview at", "offer from", "hired by", "fired from", "laid off from",
    "culture at", "management at", "ceo", "glassdoor", "blind app",
    "work-life", "compensation", "salary", "remote work", "return to office",
]


class EmployeeSentimentCollector(BaseCollector):
    """Collects employee sentiment from Reddit and Google News RSS.

    No API keys needed — uses Reddit public JSON + Google News RSS.
    Filters posts for company relevance and detects recurring issues.
    """

    def __init__(self):
        from config.settings import settings
        super().__init__(cache_ttl=settings.sentiment_cache_ttl)

    async def _fetch_raw(self, symbol: str) -> Any:
        """Fetch employee-related posts and news for the company."""
        # Resolve ticker to company name
        company_name = self._get_company_name(symbol)

        reddit_posts = await self._fetch_reddit(symbol, company_name)
        news_items = await self._fetch_news(company_name)

        return {
            "company_name": company_name,
            "symbol": symbol,
            "reddit_posts": reddit_posts,
            "news_items": news_items,
        }

    def _relevance_score(self, post: dict, company_name: str, symbol: str) -> float:
        """Score how relevant a post is to the target company's employee experience."""
        text = (post.get("title", "") + " " + post.get("selftext", "")).lower()
        company_lower = company_name.lower()
        symbol_lower = symbol.lower()

        score = 0.0

        # Company name appears in text (high relevance)
        if company_lower in text:
            score += 3.0
        # Ticker appears (only for 3+ char tickers to avoid false positives)
        if len(symbol_lower) >= 3 and symbol_lower in text:
            score += 2.0

        # Employee-related keywords present
        keyword_hits = sum(1 for kw in _EMPLOYEE_KEYWORDS if kw in text)
        score += min(keyword_hits * 0.5, 2.0)

        # Penalty if neither company name nor ticker appears
        if company_lower not in text and (len(symbol_lower) < 3 or symbol_lower not in text):
            score -= 2.0

        # Engagement bonus
        if post.get("score", 0) > 50:
            score += 0.5
        if post.get("num_comments", 0) > 20:
            score += 0.5

        return max(score, 0)

    def _detect_recurring_issues(
        self, reddit_posts: list[dict], news_items: list[dict], company_name: str
    ) -> dict:
        """Detect themes that appear in MULTIPLE distinct sources (recurring = more significant)."""
        theme_sources: dict[str, dict] = {
            theme: {"reddit": 0, "news": 0, "examples": []}
            for theme in _THEME_KEYWORDS
        }

        for post in reddit_posts:
            text = (post.get("title", "") + " " + post.get("selftext", "")).lower()
            for theme, keywords in _THEME_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    theme_sources[theme]["reddit"] += 1
                    if len(theme_sources[theme]["examples"]) < 3:
                        title = post.get("title", "")[:100]
                        theme_sources[theme]["examples"].append(f"[Reddit] {title}")

        for item in news_items:
            text = (item.get("title", "") + " " + item.get("snippet", "")).lower()
            for theme, keywords in _THEME_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    theme_sources[theme]["news"] += 1
                    if len(theme_sources[theme]["examples"]) < 3:
                        title = item.get("title", "")[:100]
                        theme_sources[theme]["examples"].append(f"[News] {title}")

        # Keep themes with multi-source confirmation OR 3+ total mentions
        recurring = {}
        for theme, data in theme_sources.items():
            total = data["reddit"] + data["news"]
            multi_source = data["reddit"] > 0 and data["news"] > 0
            if multi_source or total >= 3:
                recurring[theme] = {
                    "reddit_mentions": data["reddit"],
                    "news_mentions": data["news"],
                    "total_mentions": total,
                    "multi_source": multi_source,
                    "examples": data["examples"],
                }

        return recurring

    def _transform(self, symbol: str, raw: Any) -> dict:
        """Analyze collected data for employee sentiment themes."""
        company_name = raw["company_name"]
        reddit_posts = raw["reddit_posts"]
        news_items = raw["news_items"]

        # Filter Reddit posts by relevance
        scored_posts = []
        for post in reddit_posts:
            rel_score = self._relevance_score(post, company_name, symbol)
            if rel_score >= 1.0:
                post["_relevance"] = rel_score
                scored_posts.append(post)

        # Sort by relevance * engagement
        scored_posts.sort(
            key=lambda p: p.get("_relevance", 0) * max(p.get("score", 0), 1),
            reverse=True,
        )
        reddit_posts = scored_posts

        # Detect recurring issues across both sources
        recurring = self._detect_recurring_issues(reddit_posts, news_items, company_name)

        # Detect themes from all text
        all_text = []
        for post in reddit_posts:
            all_text.append(post.get("title", "") + " " + post.get("selftext", ""))
        for item in news_items:
            all_text.append(item.get("title", "") + " " + item.get("snippet", ""))

        combined_text = " ".join(all_text).lower()

        # Extract themes
        detected_themes = []
        for theme, keywords in _THEME_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in combined_text)
            if hits >= 1:
                detected_themes.append(theme)

        # Compute overall sentiment
        positive_themes = {"good_management", "good_culture", "innovation", "hiring_growth"}
        negative_themes = {"poor_management", "bad_culture", "stagnation", "layoffs"}
        pos_count = len(positive_themes & set(detected_themes))
        neg_count = len(negative_themes & set(detected_themes))

        if pos_count > neg_count:
            overall = "positive"
        elif neg_count > pos_count:
            overall = "negative"
        else:
            overall = "mixed"

        # Format top Reddit posts
        top_reddit = [
            f"[r/{p.get('subreddit', '?')}] {p.get('title', '')} "
            f"(score: {p.get('score', 0)}, comments: {p.get('num_comments', 0)})"
            for p in reddit_posts[:10]
        ]

        # Format news items
        formatted_news = []
        seen_titles = set()
        for item in news_items:
            title = item.get("title", "").strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                formatted_news.append(
                    NewsItem(
                        title=title,
                        source=item.get("source", ""),
                        url=item.get("url", ""),
                        published_at=item.get("published_at", ""),
                        snippet=item.get("snippet", ""),
                    )
                )

        return {
            "company_name": company_name,
            "overall_sentiment": overall,
            "key_themes": detected_themes,
            "recurring_issues": recurring,
            "mention_count": len(reddit_posts) + len(news_items),
            "reddit_posts": top_reddit,
            "news_items": formatted_news,
        }

    @staticmethod
    def _get_company_name(symbol: str) -> str:
        """Resolve ticker to company name via yfinance."""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            name = info.get("longName") or info.get("shortName") or symbol
            # Strip common suffixes for better search
            for suffix in [", Inc.", " Inc.", " Corp.", " Corporation", " Ltd.", " Limited", " PLC", " N.V.", " SE"]:
                name = name.replace(suffix, "")
            return name.strip()
        except Exception as e:
            logger.warning(f"Could not resolve company name for {symbol}: {e}")
            return symbol

    async def _fetch_reddit(self, symbol: str, company_name: str) -> list[dict]:
        """Search career subreddits for employee discussions about the company."""
        posts = []
        # Search both ticker and company name
        search_terms = [company_name]
        if company_name.upper() != symbol:
            search_terms.append(symbol)

        async with httpx.AsyncClient(
            timeout=15,
            headers={"User-Agent": "StockAnalyzer/0.1 (educational project)"},
        ) as client:
            for subreddit in EMPLOYEE_SUBREDDITS:
                for term in search_terms:
                    try:
                        url = f"https://www.reddit.com/r/{subreddit}/search.json"
                        params = {
                            "q": term,
                            "sort": "new",
                            "t": "year",  # Past year for employee sentiment
                            "limit": 10,
                            "restrict_sr": "on",
                        }
                        response = await client.get(url, params=params)

                        if response.status_code == 429:
                            logger.warning(f"Reddit rate limited on r/{subreddit}")
                            await asyncio.sleep(2)
                            continue

                        if response.status_code != 200:
                            continue

                        data = response.json()
                        children = data.get("data", {}).get("children", [])

                        for child in children:
                            post = child.get("data", {})
                            posts.append({
                                "subreddit": subreddit,
                                "title": post.get("title", ""),
                                "selftext": (post.get("selftext", "") or "")[:500],
                                "score": post.get("score", 0),
                                "num_comments": post.get("num_comments", 0),
                                "upvote_ratio": post.get("upvote_ratio", 0.5),
                                "created_utc": post.get("created_utc", 0),
                            })

                        await asyncio.sleep(1)

                    except Exception as e:
                        logger.warning(f"Reddit employee fetch failed r/{subreddit} ({term}): {e}")

        return posts

    async def _fetch_news(self, company_name: str) -> list[dict]:
        """Search Google News RSS for employee-related news."""
        articles = []

        async with httpx.AsyncClient(
            timeout=20,
            headers={"User-Agent": "StockAnalyzer/0.1 (educational project)"},
            follow_redirects=True,
        ) as client:
            for template in _NEWS_SEARCH_TEMPLATES:
                query = template.format(company=company_name)
                url = _GOOGLE_NEWS_SEARCH.format(query=quote(query))

                try:
                    response = await client.get(url)
                    if response.status_code != 200:
                        continue

                    parsed = self._parse_rss(response.text)
                    articles.extend(parsed[:10])

                except Exception as e:
                    logger.warning(f"News fetch failed for '{query}': {e}")

                await asyncio.sleep(0.5)

        return articles

    @staticmethod
    def _parse_rss(xml_text: str) -> list[dict]:
        """Parse RSS 2.0 XML into article dicts."""
        articles = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning(f"RSS parse error: {e}")
            return articles

        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pub_date_el = item.find("pubDate")
            source_el = item.find("source")
            desc_el = item.find("description")

            title = unescape(title_el.text.strip()) if title_el is not None and title_el.text else ""
            url = link_el.text.strip() if link_el is not None and link_el.text else ""
            published_at = pub_date_el.text.strip() if pub_date_el is not None and pub_date_el.text else ""
            source = source_el.text.strip() if source_el is not None and source_el.text else ""
            snippet = ""
            if desc_el is not None and desc_el.text:
                snippet = re.sub(r"<[^>]+>", " ", unescape(desc_el.text))
                snippet = re.sub(r"\s+", " ", snippet).strip()[:300]

            if title:
                articles.append({
                    "title": title,
                    "source": source,
                    "url": url,
                    "published_at": published_at,
                    "snippet": snippet,
                })

        return articles
