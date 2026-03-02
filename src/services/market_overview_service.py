"""Orchestrates market overview data collection and sector analysis."""

import logging

from src.agents.sector_analyst import SectorAnalystAgent
from src.agents.token_budget import TokenBudget
from src.data_collectors.aggregator import DataAggregator

logger = logging.getLogger(__name__)


class MarketOverviewService:
    """Collects global macro data and runs sector analysis without a specific stock."""

    def __init__(self):
        self.aggregator = DataAggregator()
        self.sector_analyst = SectorAnalystAgent()

    async def get_market_overview(self, include_sector_analysis: bool = True) -> dict:
        """Get market overview data.

        Returns dict with: economic, sentiment, data_package,
        sector_analysis (optional), tokens_used.
        """
        data_package = await self.aggregator.collect_market_overview()

        result = {
            "economic": data_package.economic,
            "sentiment": data_package.sentiment,
            "data_package": data_package,
        }

        if include_sector_analysis:
            budget = TokenBudget()
            try:
                sector = await self.sector_analyst.analyze(data_package, budget)
                result["sector_analysis"] = sector
                result["tokens_used"] = budget.total_tokens
                logger.info(f"Market overview sector analysis complete ({budget.total_tokens} tokens)")
            except Exception as e:
                logger.warning(f"Sector analysis for market overview failed: {e}")
                result["sector_analysis"] = {"error": str(e)}
                result["tokens_used"] = budget.total_tokens

        return result
