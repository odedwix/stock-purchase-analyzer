import asyncio
from typing import Any

import pandas as pd
import pandas_ta as ta
import yfinance as yf

from config.settings import settings
from src.data_collectors.base import BaseCollector
from src.models.stock_data import TechnicalData


class TechnicalCollector(BaseCollector):
    """Computes technical analysis indicators from price data."""

    def __init__(self):
        super().__init__(cache_ttl=settings.price_cache_ttl)

    async def _fetch_raw(self, symbol: str) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_sync, symbol)

    def _fetch_sync(self, symbol: str) -> pd.DataFrame:
        ticker = yf.Ticker(symbol)
        return ticker.history(period="1y")

    def _transform(self, symbol: str, raw: Any) -> TechnicalData:
        df = raw
        if df.empty:
            return TechnicalData(symbol=symbol)

        close = df["Close"]
        high = df["High"]
        low = df["Low"]

        # RSI
        rsi = ta.rsi(close, length=14)
        rsi_val = float(rsi.iloc[-1]) if rsi is not None and not rsi.empty else None

        # MACD
        macd_df = ta.macd(close)
        macd_val = macd_signal = macd_hist = None
        if macd_df is not None and not macd_df.empty:
            macd_val = float(macd_df.iloc[-1, 0])
            macd_signal = float(macd_df.iloc[-1, 1])
            macd_hist = float(macd_df.iloc[-1, 2])

        # Moving averages
        sma_20 = float(ta.sma(close, length=20).iloc[-1]) if len(close) >= 20 else None
        sma_50 = float(ta.sma(close, length=50).iloc[-1]) if len(close) >= 50 else None
        sma_200 = float(ta.sma(close, length=200).iloc[-1]) if len(close) >= 200 else None
        ema_12 = float(ta.ema(close, length=12).iloc[-1]) if len(close) >= 12 else None
        ema_26 = float(ta.ema(close, length=26).iloc[-1]) if len(close) >= 26 else None

        # Bollinger Bands
        bbands = ta.bbands(close, length=20)
        bb_upper = bb_lower = None
        if bbands is not None and not bbands.empty:
            bb_upper = float(bbands.iloc[-1, 0])  # BBU
            bb_lower = float(bbands.iloc[-1, 2])  # BBL

        # ATR
        atr = ta.atr(high, low, close, length=14)
        atr_val = float(atr.iloc[-1]) if atr is not None and not atr.empty else None

        # Simple support/resistance from recent pivots
        recent = df.tail(20)
        support = float(recent["Low"].min())
        resistance = float(recent["High"].max())

        return TechnicalData(
            symbol=symbol,
            rsi_14=rsi_val,
            macd=macd_val,
            macd_signal=macd_signal,
            macd_histogram=macd_hist,
            sma_20=sma_20,
            sma_50=sma_50,
            sma_200=sma_200,
            ema_12=ema_12,
            ema_26=ema_26,
            bollinger_upper=bb_upper,
            bollinger_lower=bb_lower,
            atr_14=atr_val,
            support_level=support,
            resistance_level=resistance,
        )
