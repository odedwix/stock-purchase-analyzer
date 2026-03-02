import asyncio
from typing import Any

import yfinance as yf

from config.settings import settings
from src.data_collectors.base import BaseCollector
from src.models.stock_data import PriceData


class PriceCollector(BaseCollector):
    """Collects current and historical price data via yfinance."""

    def __init__(self):
        super().__init__(cache_ttl=settings.price_cache_ttl)

    async def _fetch_raw(self, symbol: str) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_sync, symbol)

    def _fetch_sync(self, symbol: str) -> dict:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        hist = ticker.history(period="1y")
        return {"info": info, "history": hist}

    def _transform(self, symbol: str, raw: Any) -> PriceData:
        info = raw["info"]
        hist = raw["history"]

        history_dates = []
        history_close = []
        history_volume = []

        if not hist.empty:
            history_dates = [d.strftime("%Y-%m-%d") for d in hist.index]
            history_close = hist["Close"].tolist()
            history_volume = hist["Volume"].astype(int).tolist()

        return PriceData(
            symbol=symbol,
            current_price=info.get("currentPrice") or info.get("regularMarketPrice", 0),
            previous_close=info.get("previousClose", 0),
            open_price=info.get("open") or info.get("regularMarketOpen", 0),
            day_high=info.get("dayHigh") or info.get("regularMarketDayHigh", 0),
            day_low=info.get("dayLow") or info.get("regularMarketDayLow", 0),
            week_52_high=info.get("fiftyTwoWeekHigh", 0),
            week_52_low=info.get("fiftyTwoWeekLow", 0),
            volume=info.get("volume") or info.get("regularMarketVolume", 0),
            avg_volume=info.get("averageVolume", 0),
            market_cap=info.get("marketCap", 0),
            currency=info.get("currency", "USD"),
            history_dates=history_dates,
            history_close=history_close,
            history_volume=history_volume,
        )
