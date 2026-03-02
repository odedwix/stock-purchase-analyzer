import asyncio
import logging
from datetime import datetime

from src.data_collectors.fear_greed import FearGreedCollector
from src.data_collectors.fundamentals import FundamentalsCollector
from src.data_collectors.news_collector import NewsCollector
from src.data_collectors.price_collector import PriceCollector
from src.data_collectors.reddit_collector import RedditCollector
from src.data_collectors.technical import TechnicalCollector
from src.models.stock_data import SentimentData, StockDataPackage

logger = logging.getLogger(__name__)


class DataAggregator:
    """Runs all data collectors in parallel and assembles a StockDataPackage."""

    def __init__(self):
        self.price_collector = PriceCollector()
        self.fundamentals_collector = FundamentalsCollector()
        self.technical_collector = TechnicalCollector()
        self.news_collector = NewsCollector()
        self.reddit_collector = RedditCollector()
        self.fear_greed_collector = FearGreedCollector()

    async def collect_all(self, symbol: str) -> StockDataPackage:
        """Collect all available data for a symbol."""
        errors = []

        # Run all collectors in parallel
        results = await asyncio.gather(
            self.price_collector.collect(symbol),        # 0
            self.fundamentals_collector.collect(symbol),  # 1
            self.technical_collector.collect(symbol),     # 2
            self.news_collector.collect(symbol),          # 3
            self.reddit_collector.collect(symbol),        # 4
            self.fear_greed_collector.collect(symbol),    # 5
            return_exceptions=True,
        )

        collector_names = ["price", "fundamentals", "technical", "news", "reddit", "fear_greed"]

        # Extract results, log errors
        extracted = []
        for i, name in enumerate(collector_names):
            if isinstance(results[i], Exception):
                errors.append(f"{name}: {results[i]}")
                logger.warning(f"Collector {name} failed for {symbol}: {results[i]}")
                extracted.append(None)
            else:
                extracted.append(results[i])

        price = extracted[0]
        fundamentals = extracted[1]
        technical = extracted[2]
        news_items = extracted[3] or []
        reddit_data = extracted[4] or {}
        fear_greed = extracted[5] or (None, None)

        # Assemble sentiment data from multiple sources
        fg_score, fg_label = (None, None)
        if isinstance(fear_greed, tuple):
            fg_score, fg_label = fear_greed

        sentiment = SentimentData(
            symbol=symbol,
            fear_greed_index=fg_score,
            fear_greed_label=fg_label,
            reddit_sentiment=reddit_data.get("sentiment_score", 0) if reddit_data else 0,
            reddit_mention_count=reddit_data.get("mention_count", 0) if reddit_data else 0,
            reddit_bullish_count=reddit_data.get("bullish_count", 0) if reddit_data else 0,
            reddit_bearish_count=reddit_data.get("bearish_count", 0) if reddit_data else 0,
            reddit_subreddit_breakdown=reddit_data.get("subreddit_breakdown", {}) if reddit_data else {},
            reddit_top_posts=reddit_data.get("top_posts", []) if reddit_data else [],
            news_items=news_items,
        )

        logger.info(
            f"Data collected for {symbol}: "
            f"price={'OK' if price else 'FAIL'}, "
            f"fundamentals={'OK' if fundamentals else 'FAIL'}, "
            f"technical={'OK' if technical else 'FAIL'}, "
            f"news={len(news_items)} articles, "
            f"reddit={reddit_data.get('mention_count', 0) if reddit_data else 0} mentions, "
            f"fear_greed={fg_score}"
        )

        return StockDataPackage(
            symbol=symbol,
            price=price,
            fundamentals=fundamentals,
            technical=technical,
            sentiment=sentiment,
            collection_errors=errors,
            collected_at=datetime.now(),
        )
