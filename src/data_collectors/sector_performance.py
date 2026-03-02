"""Sector performance collector using yfinance sector ETFs.

Batch-downloads 14 sector ETFs to show which sectors are up/down today
with representative companies and tickers for each sector.
"""

import logging

import yfinance as yf

logger = logging.getLogger(__name__)

# Sector ETF map: sector name → ETF ticker + representative companies
SECTOR_MAP = {
    "Technology": {"etf": "XLK", "companies": ["AAPL", "MSFT", "NVDA", "AVGO"]},
    "Semiconductors": {"etf": "SMH", "companies": ["NVDA", "AMD", "AVGO", "TSM"]},
    "Software/SaaS": {"etf": "IGV", "companies": ["CRM", "NOW", "ADBE", "SNOW"]},
    "Energy": {"etf": "XLE", "companies": ["XOM", "CVX", "COP", "SLB"]},
    "Oil & Gas E&P": {"etf": "XOP", "companies": ["XOM", "CVX", "OXY", "DVN"]},
    "Healthcare": {"etf": "XLV", "companies": ["UNH", "JNJ", "LLY", "ABBV"]},
    "Financials": {"etf": "XLF", "companies": ["JPM", "BAC", "GS", "MS"]},
    "Consumer Discretionary": {"etf": "XLY", "companies": ["AMZN", "TSLA", "HD", "MCD"]},
    "Consumer Staples": {"etf": "XLP", "companies": ["PG", "KO", "PEP", "COST"]},
    "Industrials": {"etf": "XLI", "companies": ["CAT", "UNP", "HON", "BA"]},
    "Materials": {"etf": "XLB", "companies": ["LIN", "APD", "SHW", "FCX"]},
    "Utilities": {"etf": "XLU", "companies": ["NEE", "DUK", "SO", "AEP"]},
    "Real Estate": {"etf": "XLRE", "companies": ["PLD", "AMT", "CCI", "EQIX"]},
    "Communication": {"etf": "XLC", "companies": ["META", "GOOGL", "NFLX", "DIS"]},
}


def get_sector_performance() -> list[dict]:
    """Fetch today's performance for all sector ETFs.

    Returns a list sorted by % change (best to worst), each entry:
        {
            "sector": str,
            "etf": str,
            "change_pct": float,
            "price": float,
            "companies": list[str],
        }
    """
    etf_tickers = [info["etf"] for info in SECTOR_MAP.values()]
    ticker_str = " ".join(etf_tickers)

    try:
        # Batch download — 5 days to ensure we have a previous close
        data = yf.download(ticker_str, period="5d", progress=False, threads=True)
    except Exception as e:
        logger.error(f"yfinance sector ETF download failed: {e}")
        return []

    results = []
    for sector_name, info in SECTOR_MAP.items():
        etf = info["etf"]
        try:
            # yfinance multi-ticker returns MultiIndex columns: (field, ticker)
            if len(etf_tickers) > 1:
                close_series = data["Close"][etf].dropna()
            else:
                close_series = data["Close"].dropna()

            if len(close_series) < 2:
                continue

            current_price = float(close_series.iloc[-1])
            prev_close = float(close_series.iloc[-2])
            change_pct = ((current_price - prev_close) / prev_close) * 100

            results.append({
                "sector": sector_name,
                "etf": etf,
                "change_pct": round(change_pct, 2),
                "price": round(current_price, 2),
                "companies": info["companies"],
            })
        except Exception as e:
            logger.warning(f"Failed to process {etf} ({sector_name}): {e}")

    # Sort best to worst
    results.sort(key=lambda x: x["change_pct"], reverse=True)

    logger.info(f"Sector performance: {len(results)} sectors fetched")
    return results


def get_sector_stock_details(companies: list[str]) -> list[dict]:
    """Fetch valuation details for a list of company tickers.

    Returns a list of dicts with: ticker, price, change_pct, pe_ratio,
    from_52w_high_pct, market_cap_b, and a valuation signal.
    """
    if not companies:
        return []

    ticker_str = " ".join(companies)
    results = []

    try:
        data = yf.download(ticker_str, period="5d", progress=False, threads=True)
    except Exception as e:
        logger.error(f"yfinance stock details download failed: {e}")
        return []

    for ticker in companies:
        try:
            # Get price change
            if len(companies) > 1:
                close_series = data["Close"][ticker].dropna()
            else:
                close_series = data["Close"].dropna()

            if len(close_series) < 2:
                continue

            current_price = float(close_series.iloc[-1])
            prev_close = float(close_series.iloc[-2])
            change_pct = ((current_price - prev_close) / prev_close) * 100

            # Get fundamentals via yfinance Ticker info
            t = yf.Ticker(ticker)
            info = t.info

            pe_ratio = info.get("trailingPE")
            forward_pe = info.get("forwardPE")
            week_52_high = info.get("fiftyTwoWeekHigh", 0)
            week_52_low = info.get("fiftyTwoWeekLow", 0)
            market_cap = info.get("marketCap", 0)
            name = info.get("shortName", ticker)

            from_52w_high = 0
            if week_52_high > 0:
                from_52w_high = ((current_price - week_52_high) / week_52_high) * 100

            # Valuation signal
            signal = "neutral"
            signal_reasons = []
            if from_52w_high < -30:
                signal = "attractive"
                signal_reasons.append(f"{from_52w_high:.0f}% from 52W high")
            elif from_52w_high < -15:
                signal = "interesting"
                signal_reasons.append(f"{from_52w_high:.0f}% from 52W high")

            if pe_ratio and pe_ratio < 15:
                signal = "attractive"
                signal_reasons.append(f"low P/E {pe_ratio:.1f}")
            elif forward_pe and forward_pe < 15:
                signal = "interesting" if signal == "neutral" else signal
                signal_reasons.append(f"fwd P/E {forward_pe:.1f}")

            results.append({
                "ticker": ticker,
                "name": name,
                "price": round(current_price, 2),
                "change_pct": round(change_pct, 2),
                "pe_ratio": round(pe_ratio, 1) if pe_ratio else None,
                "forward_pe": round(forward_pe, 1) if forward_pe else None,
                "from_52w_high_pct": round(from_52w_high, 1),
                "market_cap_b": round(market_cap / 1e9, 1) if market_cap else None,
                "signal": signal,
                "signal_reasons": signal_reasons,
            })
        except Exception as e:
            logger.warning(f"Failed to get details for {ticker}: {e}")

    # Sort by signal attractiveness
    signal_order = {"attractive": 0, "interesting": 1, "neutral": 2}
    results.sort(key=lambda x: signal_order.get(x["signal"], 2))

    return results
