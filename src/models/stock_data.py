from datetime import datetime

import pandas as pd
from pydantic import BaseModel, Field


class PriceData(BaseModel):
    """Current and historical price information."""

    model_config = {"arbitrary_types_allowed": True}

    symbol: str
    current_price: float
    previous_close: float
    open_price: float
    day_high: float
    day_low: float
    week_52_high: float
    week_52_low: float
    volume: int
    avg_volume: int
    market_cap: float
    currency: str = "USD"
    timestamp: datetime = Field(default_factory=datetime.now)

    # Pre-market and after-hours
    pre_market_price: float | None = None
    pre_market_change_pct: float | None = None
    post_market_price: float | None = None
    post_market_change_pct: float | None = None

    # Multi-timeframe price changes
    change_5d_pct: float | None = None
    change_1m_pct: float | None = None
    change_3m_pct: float | None = None
    change_6m_pct: float | None = None
    change_ytd_pct: float | None = None

    # Historical data as serializable lists (converted from DataFrame)
    history_dates: list[str] = Field(default_factory=list)
    history_close: list[float] = Field(default_factory=list)
    history_volume: list[int] = Field(default_factory=list)

    # Intraday data — last 5 trading days at 1-hour intervals
    intraday_dates: list[str] = Field(default_factory=list)
    intraday_close: list[float] = Field(default_factory=list)
    intraday_volume: list[int] = Field(default_factory=list)

    @property
    def price_change_pct(self) -> float:
        if self.previous_close == 0:
            return 0.0
        return ((self.current_price - self.previous_close) / self.previous_close) * 100

    @property
    def from_52w_high_pct(self) -> float:
        if self.week_52_high == 0:
            return 0.0
        return ((self.current_price - self.week_52_high) / self.week_52_high) * 100

    @property
    def volume_vs_avg(self) -> float:
        if self.avg_volume == 0:
            return 0.0
        return self.volume / self.avg_volume


class FundamentalsData(BaseModel):
    """Key financial metrics and ratios."""

    symbol: str
    company_name: str = ""
    sector: str = ""
    industry: str = ""

    # Valuation
    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None

    # Profitability
    revenue: float | None = None
    revenue_growth: float | None = None
    net_income: float | None = None
    profit_margin: float | None = None
    operating_margin: float | None = None
    return_on_equity: float | None = None

    # Balance sheet
    total_debt: float | None = None
    total_cash: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    free_cash_flow: float | None = None

    # Dividends
    dividend_yield: float | None = None

    # Analyst targets
    analyst_target_price: float | None = None
    analyst_recommendation: str | None = None
    num_analyst_opinions: int | None = None

    # Risk & ownership (yfinance)
    beta: float | None = None
    short_percent_of_float: float | None = None
    short_ratio: float | None = None
    shares_outstanding: float | None = None
    held_pct_insiders: float | None = None
    held_pct_institutions: float | None = None
    earnings_date: str | None = None

    # SEC EDGAR insider trading (last 90 days)
    insider_buys_90d: int = 0
    insider_sells_90d: int = 0
    insider_net_shares: int = 0
    insider_transactions: list[str] = Field(default_factory=list)

    timestamp: datetime = Field(default_factory=datetime.now)


class NewsItem(BaseModel):
    """A single news article."""

    title: str
    source: str
    url: str = ""
    published_at: str = ""
    snippet: str = ""
    sentiment_score: float | None = None  # -1.0 to 1.0


class SentimentData(BaseModel):
    """Aggregated sentiment from various sources."""

    symbol: str
    fear_greed_index: int | None = None  # 0-100
    fear_greed_label: str | None = None  # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    news_sentiment: float | None = None  # -1.0 to 1.0
    reddit_sentiment: float | None = None  # -1.0 to 1.0
    reddit_mention_count: int = 0
    reddit_bullish_count: int = 0
    reddit_bearish_count: int = 0
    reddit_subreddit_breakdown: dict[str, int] = Field(default_factory=dict)
    news_items: list[NewsItem] = Field(default_factory=list)
    reddit_top_posts: list[str] = Field(default_factory=list)

    # World / geopolitical news (Google News RSS)
    world_news_items: list[NewsItem] = Field(default_factory=list)

    # Twitter / X sentiment
    twitter_sentiment: float | None = None  # -1.0 to 1.0
    twitter_mention_count: int = 0
    twitter_bullish_count: int = 0
    twitter_bearish_count: int = 0
    twitter_top_posts: list[str] = Field(default_factory=list)

    timestamp: datetime = Field(default_factory=datetime.now)


class TechnicalData(BaseModel):
    """Technical analysis indicators."""

    symbol: str
    rsi_14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_12: float | None = None
    ema_26: float | None = None
    bollinger_upper: float | None = None
    bollinger_lower: float | None = None
    atr_14: float | None = None  # Average True Range
    support_level: float | None = None
    resistance_level: float | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class EconomicData(BaseModel):
    """Macroeconomic indicators."""

    fed_funds_rate: float | None = None
    cpi_yoy: float | None = None  # year-over-year inflation
    gdp_growth: float | None = None
    unemployment_rate: float | None = None
    treasury_10y_yield: float | None = None
    treasury_2y_yield: float | None = None
    yield_curve_spread: float | None = None  # 10Y - 2Y (negative = inverted)
    vix: float | None = None
    sp500_level: float | None = None
    sp500_change_1d_pct: float | None = None
    sp500_change_1m_pct: float | None = None
    dollar_index: float | None = None
    dollar_index_change_1m_pct: float | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class StockDataPackage(BaseModel):
    """Complete data package for a stock, passed to agents for analysis."""

    symbol: str
    price: PriceData | None = None
    fundamentals: FundamentalsData | None = None
    sentiment: SentimentData | None = None
    technical: TechnicalData | None = None
    economic: EconomicData | None = None
    collection_errors: list[str] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=datetime.now)

    def to_summary_text(self) -> str:
        """Create a human-readable summary for LLM consumption."""
        parts = [f"=== Data Package for {self.symbol} ===\n"]

        if self.price:
            p = self.price
            parts.append(f"PRICE: ${p.current_price:.2f}")
            parts.append(f"  Change (1D): {p.price_change_pct:+.2f}%")
            if p.pre_market_price is not None:
                chg = f" ({p.pre_market_change_pct:+.2f}%)" if p.pre_market_change_pct is not None else ""
                parts.append(f"  Pre-Market: ${p.pre_market_price:.2f}{chg}")
            if p.post_market_price is not None:
                chg = f" ({p.post_market_change_pct:+.2f}%)" if p.post_market_change_pct is not None else ""
                parts.append(f"  After-Hours: ${p.post_market_price:.2f}{chg}")
            # Multi-timeframe changes
            tf_parts = []
            if p.change_5d_pct is not None:
                tf_parts.append(f"5D: {p.change_5d_pct:+.2f}%")
            if p.change_1m_pct is not None:
                tf_parts.append(f"1M: {p.change_1m_pct:+.2f}%")
            if p.change_3m_pct is not None:
                tf_parts.append(f"3M: {p.change_3m_pct:+.2f}%")
            if p.change_6m_pct is not None:
                tf_parts.append(f"6M: {p.change_6m_pct:+.2f}%")
            if p.change_ytd_pct is not None:
                tf_parts.append(f"YTD: {p.change_ytd_pct:+.2f}%")
            if tf_parts:
                parts.append(f"  Timeframe Changes: {' | '.join(tf_parts)}")
            parts.append(f"  52W Range: ${p.week_52_low:.2f} - ${p.week_52_high:.2f}")
            parts.append(f"  From 52W High: {p.from_52w_high_pct:.1f}%")
            parts.append(f"  Volume vs Avg: {p.volume_vs_avg:.2f}x")
            parts.append(f"  Market Cap: ${p.market_cap:,.0f}")
            # Intraday summary
            if p.intraday_close:
                intraday_high = max(p.intraday_close)
                intraday_low = min(p.intraday_close)
                parts.append(f"  Intraday 5D Range (hourly): ${intraday_low:.2f} - ${intraday_high:.2f} ({len(p.intraday_close)} bars)")
            parts.append("")

        if self.fundamentals:
            f = self.fundamentals
            parts.append(f"FUNDAMENTALS ({f.company_name}, {f.sector}):")
            if f.pe_ratio is not None:
                parts.append(f"  P/E: {f.pe_ratio:.1f}")
            if f.forward_pe is not None:
                parts.append(f"  Forward P/E: {f.forward_pe:.1f}")
            if f.revenue is not None:
                parts.append(f"  Revenue: ${f.revenue:,.0f}")
            if f.revenue_growth is not None:
                parts.append(f"  Revenue Growth: {f.revenue_growth:.1%}")
            if f.profit_margin is not None:
                parts.append(f"  Profit Margin: {f.profit_margin:.1%}")
            if f.debt_to_equity is not None:
                parts.append(f"  Debt/Equity: {f.debt_to_equity:.2f}")
            if f.free_cash_flow is not None:
                parts.append(f"  Free Cash Flow: ${f.free_cash_flow:,.0f}")
            if f.analyst_target_price is not None:
                parts.append(f"  Analyst Target: ${f.analyst_target_price:.2f}")
            if f.analyst_recommendation:
                parts.append(f"  Analyst Rec: {f.analyst_recommendation}")
            if f.beta is not None:
                parts.append(f"  Beta: {f.beta:.2f}")
            if f.short_percent_of_float is not None:
                parts.append(f"  Short Interest: {f.short_percent_of_float:.1%} of float")
            if f.short_ratio is not None:
                parts.append(f"  Short Ratio (Days to Cover): {f.short_ratio:.1f}")
            if f.held_pct_insiders is not None:
                parts.append(f"  Insider Ownership: {f.held_pct_insiders:.1%}")
            if f.held_pct_institutions is not None:
                parts.append(f"  Institutional Ownership: {f.held_pct_institutions:.1%}")
            if f.earnings_date:
                parts.append(f"  Next Earnings Date: {f.earnings_date}")
            if f.insider_buys_90d or f.insider_sells_90d:
                net = f.insider_buys_90d - f.insider_sells_90d
                signal = "NET BUYING" if net > 0 else ("NET SELLING" if net < 0 else "NEUTRAL")
                parts.append(f"  Insider Trades (90d): {f.insider_buys_90d} buys, {f.insider_sells_90d} sells [{signal}]")
                for txn in f.insider_transactions[:5]:
                    parts.append(f"    - {txn}")
            parts.append("")

        if self.technical:
            t = self.technical
            parts.append("TECHNICAL INDICATORS:")
            if t.rsi_14 is not None:
                parts.append(f"  RSI(14): {t.rsi_14:.1f}")
            if t.macd is not None:
                parts.append(f"  MACD: {t.macd:.3f} (Signal: {t.macd_signal:.3f})")
            if t.sma_50 is not None and t.sma_200 is not None:
                parts.append(f"  SMA 50/200: ${t.sma_50:.2f} / ${t.sma_200:.2f}")
            if t.support_level is not None:
                parts.append(f"  Support: ${t.support_level:.2f}")
            if t.resistance_level is not None:
                parts.append(f"  Resistance: ${t.resistance_level:.2f}")
            parts.append("")

        if self.sentiment:
            s = self.sentiment
            parts.append("SENTIMENT:")
            if s.fear_greed_index is not None:
                parts.append(f"  Fear & Greed Index: {s.fear_greed_index} ({s.fear_greed_label})")
            if s.reddit_mention_count > 0:
                parts.append(f"  Reddit Mentions: {s.reddit_mention_count}")
                parts.append(f"  Reddit Sentiment: {s.reddit_sentiment:+.2f}")
                if s.reddit_bullish_count or s.reddit_bearish_count:
                    parts.append(f"  Reddit Bullish/Bearish: {s.reddit_bullish_count}/{s.reddit_bearish_count}")
                if s.reddit_subreddit_breakdown:
                    breakdown = ", ".join(f"r/{sub}: {cnt}" for sub, cnt in s.reddit_subreddit_breakdown.items())
                    parts.append(f"  Subreddit Breakdown: {breakdown}")
            if s.twitter_mention_count > 0:
                parts.append(f"  Twitter/X Mentions: {s.twitter_mention_count}")
                parts.append(f"  Twitter Sentiment: {s.twitter_sentiment:+.2f}")
                if s.twitter_bullish_count or s.twitter_bearish_count:
                    parts.append(f"  Twitter Bullish/Bearish: {s.twitter_bullish_count}/{s.twitter_bearish_count}")
            if s.news_items:
                parts.append(f"  Stock News ({len(s.news_items)} articles):")
                for item in s.news_items[:5]:
                    parts.append(f"    - {item.title} ({item.source})")
            if s.world_news_items:
                parts.append(f"  World News ({len(s.world_news_items)} articles):")
                for item in s.world_news_items[:5]:
                    parts.append(f"    - {item.title} ({item.source})")
            parts.append("")

        if self.economic:
            e = self.economic
            parts.append("MACRO ECONOMY:")
            if e.fed_funds_rate is not None:
                parts.append(f"  Fed Funds Rate: {e.fed_funds_rate:.2f}%")
            if e.cpi_yoy is not None:
                parts.append(f"  CPI (YoY): {e.cpi_yoy:.1f}%")
            if e.treasury_10y_yield is not None:
                parts.append(f"  10Y Treasury Yield: {e.treasury_10y_yield:.2f}%")
            if e.treasury_2y_yield is not None:
                parts.append(f"  2Y Treasury Yield: {e.treasury_2y_yield:.2f}%")
            if e.yield_curve_spread is not None:
                curve_status = "INVERTED (recession warning)" if e.yield_curve_spread < 0 else "NORMAL"
                parts.append(f"  Yield Curve (10Y-2Y): {e.yield_curve_spread:+.2f}% [{curve_status}]")
            if e.vix is not None:
                vix_level = "LOW (<15)" if e.vix < 15 else ("ELEVATED (15-25)" if e.vix < 25 else "HIGH (>25)")
                parts.append(f"  VIX (Fear Gauge): {e.vix:.1f} [{vix_level}]")
            if e.sp500_level is not None:
                parts.append(f"  S&P 500: {e.sp500_level:,.1f}")
                if e.sp500_change_1d_pct is not None:
                    parts.append(f"    1D Change: {e.sp500_change_1d_pct:+.2f}%")
                if e.sp500_change_1m_pct is not None:
                    parts.append(f"    1M Change: {e.sp500_change_1m_pct:+.2f}%")
            if e.dollar_index is not None:
                parts.append(f"  Dollar Index (DXY): {e.dollar_index:.1f}")
                if e.dollar_index_change_1m_pct is not None:
                    parts.append(f"    1M Change: {e.dollar_index_change_1m_pct:+.2f}%")
            parts.append("")

        if self.collection_errors:
            parts.append(f"DATA GAPS: {', '.join(self.collection_errors)}")

        return "\n".join(parts)
