"""Collects macroeconomic indicators via yfinance market tickers. No API key needed."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import yfinance as yf

from config.settings import settings
from src.data_collectors.base import BaseCollector
from src.models.stock_data import EconomicData

logger = logging.getLogger(__name__)

# Market tickers for macro indicators
MARKET_TICKERS = {
    "^VIX": "vix",
    "^TNX": "treasury_10y",  # 10-Year Treasury yield (x10)
    "^IRX": "treasury_13w",  # 13-Week T-Bill (proxy for short-term rates, x10)
    "^TYX": "treasury_2y",   # Use 30Y as proxy; we also try ^TWO for 2Y
    "^GSPC": "sp500",        # S&P 500
    "DX-Y.NYB": "dollar",    # US Dollar Index
}


class EconomicCollector(BaseCollector):
    """Collects VIX, Treasury yields, S&P 500, and Dollar Index via yfinance."""

    def __init__(self):
        super().__init__(cache_ttl=settings.sentiment_cache_ttl)

    def _cache_key(self, symbol: str) -> str:
        return "EconomicCollector:global"  # Not per-symbol — global macro data

    async def _fetch_raw(self, symbol: str) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_sync)

    def _fetch_sync(self) -> dict:
        data = {}
        tickers_str = " ".join(MARKET_TICKERS.keys())

        try:
            tickers = yf.Tickers(tickers_str)
            for ticker_symbol, label in MARKET_TICKERS.items():
                try:
                    t = tickers.tickers.get(ticker_symbol)
                    if t is None:
                        continue
                    info = t.info
                    price = info.get("regularMarketPrice") or info.get("previousClose")
                    prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
                    data[label] = {
                        "price": price,
                        "prev_close": prev_close,
                    }
                except Exception as e:
                    logger.debug(f"Failed to fetch {ticker_symbol}: {e}")
        except Exception as e:
            logger.warning(f"Batch ticker fetch failed, trying individually: {e}")
            for ticker_symbol, label in MARKET_TICKERS.items():
                try:
                    t = yf.Ticker(ticker_symbol)
                    info = t.info
                    price = info.get("regularMarketPrice") or info.get("previousClose")
                    prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
                    data[label] = {"price": price, "prev_close": prev_close}
                except Exception as e2:
                    logger.debug(f"Failed to fetch {ticker_symbol}: {e2}")

        # Get 1-month history for S&P 500 and Dollar Index to compute changes
        for ticker_symbol, label in [("^GSPC", "sp500"), ("DX-Y.NYB", "dollar")]:
            try:
                t = yf.Ticker(ticker_symbol)
                hist = t.history(period="1mo")
                if len(hist) >= 2:
                    data[f"{label}_1m_ago"] = float(hist["Close"].iloc[0])
            except Exception as e:
                logger.debug(f"Failed to fetch history for {ticker_symbol}: {e}")

        # Try to get 2-year treasury yield
        try:
            t = yf.Ticker("^TWO")
            info = t.info
            price = info.get("regularMarketPrice") or info.get("previousClose")
            if price:
                data["treasury_2y"] = {"price": price}
        except Exception:
            pass

        return data

    def _transform(self, symbol: str, raw: Any) -> EconomicData:
        if not raw:
            return EconomicData()

        vix = None
        if "vix" in raw and raw["vix"].get("price"):
            vix = raw["vix"]["price"]

        # Treasury yields — ^TNX and ^IRX are quoted x10 (e.g., 45.2 = 4.52%)
        treasury_10y = None
        if "treasury_10y" in raw and raw["treasury_10y"].get("price"):
            treasury_10y = raw["treasury_10y"]["price"] / 10.0

        fed_funds_approx = None
        if "treasury_13w" in raw and raw["treasury_13w"].get("price"):
            fed_funds_approx = raw["treasury_13w"]["price"] / 10.0

        treasury_2y = None
        if "treasury_2y" in raw and raw["treasury_2y"].get("price"):
            val = raw["treasury_2y"]["price"]
            # ^TWO is already in percentage terms (not x10)
            treasury_2y = val if val < 20 else val / 10.0

        yield_curve_spread = None
        if treasury_10y is not None and treasury_2y is not None:
            yield_curve_spread = treasury_10y - treasury_2y

        sp500_level = None
        sp500_1d_pct = None
        sp500_1m_pct = None
        if "sp500" in raw and raw["sp500"].get("price"):
            sp500_level = raw["sp500"]["price"]
            prev = raw["sp500"].get("prev_close")
            if prev and prev > 0:
                sp500_1d_pct = ((sp500_level - prev) / prev) * 100
            if "sp500_1m_ago" in raw and raw["sp500_1m_ago"] > 0:
                sp500_1m_pct = ((sp500_level - raw["sp500_1m_ago"]) / raw["sp500_1m_ago"]) * 100

        dollar_index = None
        dollar_1m_pct = None
        if "dollar" in raw and raw["dollar"].get("price"):
            dollar_index = raw["dollar"]["price"]
            if "dollar_1m_ago" in raw and raw["dollar_1m_ago"] > 0:
                dollar_1m_pct = ((dollar_index - raw["dollar_1m_ago"]) / raw["dollar_1m_ago"]) * 100

        return EconomicData(
            vix=vix,
            treasury_10y_yield=treasury_10y,
            fed_funds_rate=fed_funds_approx,
            treasury_2y_yield=treasury_2y,
            yield_curve_spread=yield_curve_spread,
            sp500_level=sp500_level,
            sp500_change_1d_pct=sp500_1d_pct,
            sp500_change_1m_pct=sp500_1m_pct,
            dollar_index=dollar_index,
            dollar_index_change_1m_pct=dollar_1m_pct,
        )
