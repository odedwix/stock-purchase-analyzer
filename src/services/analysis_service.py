import logging

from src.agents.debate_engine import DebateEngine
from src.data_collectors.aggregator import DataAggregator
from src.models.analysis import DebateTranscript
from src.utils.stock_filters import validate_ticker

logger = logging.getLogger(__name__)


class AnalysisService:
    """Top-level orchestrator: data collection → debate → recommendation."""

    def __init__(self):
        self.data_aggregator = DataAggregator()
        self.debate_engine = DebateEngine()

    async def analyze_stock(self, symbol: str) -> DebateTranscript:
        """Run a full analysis for a stock symbol."""
        symbol = symbol.upper().strip()

        # Validate ticker
        is_valid, reason = await validate_ticker(symbol)
        if not is_valid:
            raise ValueError(f"Invalid ticker {symbol}: {reason}")

        logger.info(f"Starting analysis for {symbol}")

        # Collect data
        logger.info(f"Collecting data for {symbol}...")
        data_package = await self.data_aggregator.collect_all(symbol)

        if data_package.price is None and data_package.fundamentals is None:
            raise ValueError(
                f"Could not collect any data for {symbol}. "
                f"Errors: {', '.join(data_package.collection_errors)}"
            )

        # Run debate
        logger.info(f"Running agent debate for {symbol}...")
        transcript = await self.debate_engine.run_debate(data_package)

        return transcript
