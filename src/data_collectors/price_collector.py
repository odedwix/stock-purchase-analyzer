import asyncio
from datetime import datetime
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
        hist_intraday = ticker.history(period="5d", interval="1h")
        return {"info": info, "history": hist, "intraday": hist_intraday}

    @staticmethod
    def _compute_timeframe_changes(history_close: list[float], history_dates: list[str]) -> dict:
        """Compute price changes over multiple timeframes from daily history data."""
        changes: dict[str, float | None] = {
            "change_5d_pct": None,
            "change_1m_pct": None,
            "change_3m_pct": None,
            "change_6m_pct": None,
            "change_ytd_pct": None,
        }
        if not history_close or not history_dates:
            return changes

        current = history_close[-1]
        n = len(history_close)

        # 1-day change is already handled by price_change_pct property.
        # 5-day: approximately 5 trading days
        if n >= 5:
            changes["change_5d_pct"] = round(((current - history_close[-5]) / history_close[-5]) * 100, 2)

        # 1-month: approximately 21 trading days
        if n >= 21:
            changes["change_1m_pct"] = round(((current - history_close[-21]) / history_close[-21]) * 100, 2)

        # 3-month: approximately 63 trading days
        if n >= 63:
            changes["change_3m_pct"] = round(((current - history_close[-63]) / history_close[-63]) * 100, 2)

        # 6-month: approximately 126 trading days
        if n >= 126:
            changes["change_6m_pct"] = round(((current - history_close[-126]) / history_close[-126]) * 100, 2)

        # YTD: find the first trading day of the current year
        current_year = str(datetime.now().year)
        for i, date_str in enumerate(history_dates):
            if date_str.startswith(current_year):
                ytd_start = history_close[i]
                if ytd_start != 0:
                    changes["change_ytd_pct"] = round(((current - ytd_start) / ytd_start) * 100, 2)
                break

        return changes

    def _transform(self, symbol: str, raw: Any) -> PriceData:
        info = raw["info"]
        hist = raw["history"]
        hist_intraday = raw.get("intraday")

        history_dates = []
        history_close = []
        history_volume = []

        if not hist.empty:
            history_dates = [d.strftime("%Y-%m-%d") for d in hist.index]
            history_close = hist["Close"].tolist()
            history_volume = hist["Volume"].astype(int).tolist()

        # Intraday data (5-day hourly)
        intraday_dates = []
        intraday_close = []
        intraday_volume = []

        if hist_intraday is not None and not hist_intraday.empty:
            intraday_dates = [d.strftime("%Y-%m-%d %H:%M") for d in hist_intraday.index]
            intraday_close = hist_intraday["Close"].tolist()
            intraday_volume = hist_intraday["Volume"].astype(int).tolist()

        # Pre-market and post-market data
        pre_market_price = info.get("preMarketPrice")
        pre_market_change_pct = info.get("preMarketChangePercent")
        # Convert from decimal to percentage if provided as a decimal (e.g. 0.02 -> 2.0)
        if pre_market_change_pct is not None and abs(pre_market_change_pct) < 1:
            pre_market_change_pct = round(pre_market_change_pct * 100, 2)

        post_market_price = info.get("postMarketPrice")
        post_market_change_pct = info.get("postMarketChangePercent")
        if post_market_change_pct is not None and abs(post_market_change_pct) < 1:
            post_market_change_pct = round(post_market_change_pct * 100, 2)

        # Multi-timeframe changes
        timeframe_changes = self._compute_timeframe_changes(history_close, history_dates)

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
            pre_market_price=pre_market_price,
            pre_market_change_pct=pre_market_change_pct,
            post_market_price=post_market_price,
            post_market_change_pct=post_market_change_pct,
            change_5d_pct=timeframe_changes["change_5d_pct"],
            change_1m_pct=timeframe_changes["change_1m_pct"],
            change_3m_pct=timeframe_changes["change_3m_pct"],
            change_6m_pct=timeframe_changes["change_6m_pct"],
            change_ytd_pct=timeframe_changes["change_ytd_pct"],
            history_dates=history_dates,
            history_close=history_close,
            history_volume=history_volume,
            intraday_dates=intraday_dates,
            intraday_close=intraday_close,
            intraday_volume=intraday_volume,
        )
