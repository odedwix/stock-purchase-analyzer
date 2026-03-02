import asyncio
import logging
from datetime import datetime

from src.data_collectors.fundamentals import FundamentalsCollector
from src.data_collectors.price_collector import PriceCollector
from src.data_collectors.technical import TechnicalCollector
from src.models.stock_data import StockDataPackage

logger = logging.getLogger(__name__)


class DataAggregator:
    """Runs all data collectors in parallel and assembles a StockDataPackage."""

    def __init__(self):
        self.price_collector = PriceCollector()
        self.fundamentals_collector = FundamentalsCollector()
        self.technical_collector = TechnicalCollector()
        # Sentiment, news, economic collectors added in Phase 2

    async def collect_all(self, symbol: str) -> StockDataPackage:
        """Collect all available data for a symbol."""
        errors = []

        results = await asyncio.gather(
            self.price_collector.collect(symbol),
            self.fundamentals_collector.collect(symbol),
            self.technical_collector.collect(symbol),
            return_exceptions=True,
        )

        price = results[0] if not isinstance(results[0], Exception) else None
        fundamentals = results[1] if not isinstance(results[1], Exception) else None
        technical = results[2] if not isinstance(results[2], Exception) else None

        for i, name in enumerate(["price", "fundamentals", "technical"]):
            if isinstance(results[i], Exception):
                errors.append(f"{name}: {results[i]}")
                logger.warning(f"Collector {name} failed for {symbol}: {results[i]}")

        return StockDataPackage(
            symbol=symbol,
            price=price,
            fundamentals=fundamentals,
            technical=technical,
            collection_errors=errors,
            collected_at=datetime.now(),
        )
