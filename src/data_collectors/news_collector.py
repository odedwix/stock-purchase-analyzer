import asyncio
import logging
from datetime import datetime
from typing import Any

from src.data_collectors.base import BaseCollector
from src.models.stock_data import NewsItem, SentimentData

logger = logging.getLogger(__name__)


class NewsCollector(BaseCollector):
    """Collects recent news for a stock via finvizfinance (no API key needed)."""

    def __init__(self):
        from config.settings import settings

        super().__init__(cache_ttl=settings.news_cache_ttl)

    async def _fetch_raw(self, symbol: str) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_sync, symbol)

    def _fetch_sync(self, symbol: str) -> list[dict]:
        try:
            from finvizfinance.quote import finvizfinance

            stock = finvizfinance(symbol)
            news_df = stock.ticker_news()

            if news_df is None or news_df.empty:
                return []

            results = []
            for _, row in news_df.iterrows():
                results.append({
                    "title": str(row.get("Title", "")),
                    "source": str(row.get("Source", "")),
                    "url": str(row.get("Link", "")),
                    "date": str(row.get("Date", "")),
                })

            return results[:30]  # Last 30 news items
        except Exception as e:
            logger.warning(f"finvizfinance news failed for {symbol}: {e}")
            return []

    def _transform(self, symbol: str, raw: Any) -> list[NewsItem]:
        items = []
        for article in raw:
            items.append(NewsItem(
                title=article.get("title", ""),
                source=article.get("source", ""),
                url=article.get("url", ""),
                published_at=article.get("date", ""),
            ))
        return items
