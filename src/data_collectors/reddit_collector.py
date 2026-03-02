import asyncio
import logging
import re
from typing import Any

import httpx

from src.data_collectors.base import BaseCollector

logger = logging.getLogger(__name__)

# Subreddits to monitor for stock sentiment
SUBREDDITS = [
    "stocks", "investing", "wallstreetbets", "StockMarket",
    "options", "dividends", "ValueInvesting", "SecurityAnalysis",
]


class RedditCollector(BaseCollector):
    """Collects Reddit sentiment via public JSON API (no authentication needed).

    Uses Reddit's public .json endpoint which doesn't require API keys.
    Rate limited but sufficient for periodic analysis.
    """

    def __init__(self):
        from config.settings import settings

        super().__init__(cache_ttl=settings.sentiment_cache_ttl)

    async def _fetch_raw(self, symbol: str) -> Any:
        posts = []
        async with httpx.AsyncClient(
            timeout=15,
            headers={"User-Agent": "StockAnalyzer/0.1 (educational project)"},
        ) as client:
            for subreddit in SUBREDDITS:
                try:
                    # Search for the ticker in each subreddit
                    url = f"https://www.reddit.com/r/{subreddit}/search.json"
                    params = {
                        "q": symbol,
                        "sort": "new",
                        "t": "week",  # Past week
                        "limit": 15,
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
                            "url": f"https://reddit.com{post.get('permalink', '')}",
                        })

                    # Be polite to Reddit's servers
                    await asyncio.sleep(1)

                except Exception as e:
                    logger.warning(f"Reddit fetch failed for r/{subreddit}: {e}")

        return posts

    def _transform(self, symbol: str, raw: Any) -> dict:
        """Transform raw Reddit posts into sentiment summary."""
        posts = raw
        if not posts:
            return {
                "mention_count": 0,
                "sentiment_score": 0,
                "top_posts": [],
                "bullish_count": 0,
                "bearish_count": 0,
                "subreddit_breakdown": {},
            }

        # Simple keyword-based sentiment (works well enough for stock discussions)
        bullish_words = {
            "buy", "bull", "bullish", "long", "calls", "moon", "rocket", "undervalued",
            "breakout", "support", "accumulate", "dip", "opportunity", "upside", "growth",
            "strong", "beat", "earnings", "upgrade", "outperform",
        }
        bearish_words = {
            "sell", "bear", "bearish", "short", "puts", "crash", "overvalued", "bubble",
            "resistance", "dump", "downgrade", "risk", "decline", "weak", "miss",
            "downside", "fear", "recession", "layoffs", "lawsuit",
        }

        bullish_count = 0
        bearish_count = 0
        total_score = 0
        subreddit_counts = {}

        for post in posts:
            text = (post["title"] + " " + post["selftext"]).lower()
            bull_hits = sum(1 for w in bullish_words if w in text)
            bear_hits = sum(1 for w in bearish_words if w in text)

            if bull_hits > bear_hits:
                bullish_count += 1
                total_score += post["upvote_ratio"]
            elif bear_hits > bull_hits:
                bearish_count += 1
                total_score -= post["upvote_ratio"]

            sub = post["subreddit"]
            subreddit_counts[sub] = subreddit_counts.get(sub, 0) + 1

        # Normalize sentiment to -1.0 to 1.0
        total = bullish_count + bearish_count
        sentiment = 0.0
        if total > 0:
            sentiment = (bullish_count - bearish_count) / total

        # Top posts by engagement (score * num_comments)
        sorted_posts = sorted(posts, key=lambda p: p["score"] * max(p["num_comments"], 1), reverse=True)
        top_posts = [
            f"[r/{p['subreddit']}] {p['title']} (score: {p['score']}, comments: {p['num_comments']})"
            for p in sorted_posts[:10]
        ]

        return {
            "mention_count": len(posts),
            "sentiment_score": round(sentiment, 3),
            "top_posts": top_posts,
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "subreddit_breakdown": subreddit_counts,
        }
