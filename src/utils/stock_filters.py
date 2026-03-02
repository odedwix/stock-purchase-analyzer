import asyncio
import logging

import yfinance as yf

from config.settings import settings

logger = logging.getLogger(__name__)

# Well-known ETFs that should bypass market cap filter
KNOWN_ETFS = {
    "JETS", "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "VGT", "XLK", "XLF",
    "XLE", "ARKK", "ARKG", "SOXX", "SMH", "TLT", "GLD", "SLV",
}


async def validate_ticker(symbol: str) -> tuple[bool, str]:
    """Validate a ticker symbol. Returns (is_valid, reason)."""
    symbol = symbol.upper().strip()

    if not symbol or not symbol.isalpha():
        return False, "Invalid ticker format"

    # ETFs bypass market cap filter
    if symbol in KNOWN_ETFS:
        return True, "Known ETF"

    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(None, _get_info, symbol)
    except Exception as e:
        return False, f"Could not fetch data: {e}"

    if not info or info.get("regularMarketPrice") is None:
        return False, "Ticker not found or no market data"

    market_cap = info.get("marketCap", 0)
    quote_type = info.get("quoteType", "")

    # ETFs don't have market cap in the same way
    if quote_type == "ETF":
        return True, "ETF"

    if market_cap and market_cap < settings.min_market_cap:
        return False, f"Market cap ${market_cap:,.0f} below minimum ${settings.min_market_cap:,.0f}"

    return True, "Valid"


def _get_info(symbol: str) -> dict:
    return yf.Ticker(symbol).info
