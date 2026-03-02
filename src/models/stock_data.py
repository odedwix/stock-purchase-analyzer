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

    # Historical data as serializable lists (converted from DataFrame)
    history_dates: list[str] = Field(default_factory=list)
    history_close: list[float] = Field(default_factory=list)
    history_volume: list[int] = Field(default_factory=list)

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
    news_items: list[NewsItem] = Field(default_factory=list)
    reddit_top_posts: list[str] = Field(default_factory=list)
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
    vix: float | None = None
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
            parts.append(f"PRICE: ${self.price.current_price:.2f}")
            parts.append(f"  Change: {self.price.price_change_pct:+.2f}%")
            parts.append(f"  52W Range: ${self.price.week_52_low:.2f} - ${self.price.week_52_high:.2f}")
            parts.append(f"  From 52W High: {self.price.from_52w_high_pct:.1f}%")
            parts.append(f"  Volume vs Avg: {self.price.volume_vs_avg:.2f}x")
            parts.append(f"  Market Cap: ${self.price.market_cap:,.0f}\n")

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
            if s.news_items:
                parts.append(f"  Recent News ({len(s.news_items)} articles):")
                for item in s.news_items[:5]:
                    parts.append(f"    - {item.title} ({item.source})")
            parts.append("")

        if self.economic:
            e = self.economic
            parts.append("MACRO ECONOMY:")
            if e.fed_funds_rate is not None:
                parts.append(f"  Fed Funds Rate: {e.fed_funds_rate:.2f}%")
            if e.cpi_yoy is not None:
                parts.append(f"  CPI (YoY): {e.cpi_yoy:.1f}%")
            if e.vix is not None:
                parts.append(f"  VIX: {e.vix:.1f}")
            parts.append("")

        if self.collection_errors:
            parts.append(f"DATA GAPS: {', '.join(self.collection_errors)}")

        return "\n".join(parts)
