import asyncio
from typing import Any

import yfinance as yf

from config.settings import settings
from src.data_collectors.base import BaseCollector
from src.models.stock_data import FundamentalsData


class FundamentalsCollector(BaseCollector):
    """Collects fundamental financial data via yfinance."""

    def __init__(self):
        super().__init__(cache_ttl=settings.fundamentals_cache_ttl)

    async def _fetch_raw(self, symbol: str) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_sync, symbol)

    def _fetch_sync(self, symbol: str) -> dict:
        ticker = yf.Ticker(symbol)
        return ticker.info

    def _transform(self, symbol: str, raw: Any) -> FundamentalsData:
        info = raw
        return FundamentalsData(
            symbol=symbol,
            company_name=info.get("longName", info.get("shortName", "")),
            sector=info.get("sector", ""),
            industry=info.get("industry", ""),
            # Valuation
            pe_ratio=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            peg_ratio=info.get("pegRatio"),
            price_to_book=info.get("priceToBook"),
            price_to_sales=info.get("priceToSalesTrailing12Months"),
            # Profitability
            revenue=info.get("totalRevenue"),
            revenue_growth=info.get("revenueGrowth"),
            net_income=info.get("netIncomeToCommon"),
            profit_margin=info.get("profitMargins"),
            operating_margin=info.get("operatingMargins"),
            return_on_equity=info.get("returnOnEquity"),
            # Balance sheet
            total_debt=info.get("totalDebt"),
            total_cash=info.get("totalCash"),
            debt_to_equity=info.get("debtToEquity"),
            current_ratio=info.get("currentRatio"),
            free_cash_flow=info.get("freeCashflow"),
            # Dividends
            dividend_yield=info.get("dividendYield"),
            # Analyst
            analyst_target_price=info.get("targetMeanPrice"),
            analyst_recommendation=info.get("recommendationKey"),
            num_analyst_opinions=info.get("numberOfAnalystOpinions"),
        )
