from src.agents.base_agent import BaseAgent
from src.models.stock_data import StockDataPackage


class MacroEconomistAgent(BaseAgent):
    """Macroeconomic and geopolitical analyst."""

    def __init__(self, **kwargs):
        super().__init__(
            name="Macro Economist",
            prompt_file="macro_economist.md",
            **kwargs,
        )

    def _format_data(self, data: StockDataPackage) -> str:
        """Send economic data, news, and company context for macro analysis."""
        parts = [f"=== Macro & Geopolitical Context for {data.symbol} ===\n"]

        # Company context
        if data.fundamentals:
            f = data.fundamentals
            parts.append(f"COMPANY: {f.company_name}")
            parts.append(f"  Sector: {f.sector} / {f.industry}")
            if f.revenue is not None:
                parts.append(f"  Revenue: ${f.revenue:,.0f}")
            if f.revenue_growth is not None:
                parts.append(f"  Revenue Growth: {f.revenue_growth:.1%}")
            if f.debt_to_equity is not None:
                parts.append(f"  Debt/Equity: {f.debt_to_equity:.2f}")
            if f.business_description:
                parts.append(f"  Business: {f.business_description[:300]}")
            if f.full_time_employees:
                parts.append(f"  Employees: {f.full_time_employees:,}")
            parts.append("")

        if data.price:
            p = data.price
            parts.append(f"CURRENT PRICE: ${p.current_price:.2f}")
            parts.append(f"  Market Cap: ${p.market_cap:,.0f}")
            parts.append(f"  Change Today: {p.price_change_pct:+.2f}%")
            parts.append(f"  From 52W High: {p.from_52w_high_pct:.1f}%")

            if p.pre_market_price:
                parts.append(f"  Pre-Market: ${p.pre_market_price:.2f} ({p.pre_market_change_pct:+.2f}%)")

            # Multi-timeframe for macro context
            timeframes = []
            if p.change_1m_pct is not None:
                timeframes.append(f"1M: {p.change_1m_pct:+.1f}%")
            if p.change_3m_pct is not None:
                timeframes.append(f"3M: {p.change_3m_pct:+.1f}%")
            if p.change_6m_pct is not None:
                timeframes.append(f"6M: {p.change_6m_pct:+.1f}%")
            if p.change_ytd_pct is not None:
                timeframes.append(f"YTD: {p.change_ytd_pct:+.1f}%")
            if timeframes:
                parts.append(f"  Performance: {' | '.join(timeframes)}")
            parts.append("")

        # Economic data
        if data.economic:
            e = data.economic
            parts.append("MACRO INDICATORS:")
            if e.fed_funds_rate is not None:
                parts.append(f"  Fed Funds Rate (approx): {e.fed_funds_rate:.2f}%")
            if e.cpi_yoy is not None:
                parts.append(f"  CPI (YoY): {e.cpi_yoy:.1f}%")
                if e.fed_funds_rate is not None:
                    real_rate = e.fed_funds_rate - e.cpi_yoy
                    parts.append(f"  Real Interest Rate: {real_rate:+.1f}%")
            if e.gdp_growth is not None:
                parts.append(f"  GDP Growth: {e.gdp_growth:.1f}%")
            if e.unemployment_rate is not None:
                parts.append(f"  Unemployment: {e.unemployment_rate:.1f}%")
            if e.treasury_10y_yield is not None:
                parts.append(f"  10Y Treasury Yield: {e.treasury_10y_yield:.2f}%")
            if e.treasury_2y_yield is not None:
                parts.append(f"  2Y Treasury Yield: {e.treasury_2y_yield:.2f}%")
            if e.yield_curve_spread is not None:
                if e.yield_curve_spread < 0:
                    curve_signal = "INVERTED — historically precedes recessions by 6-18 months"
                elif e.yield_curve_spread < 0.5:
                    curve_signal = "FLAT — late-cycle signal, watch closely"
                else:
                    curve_signal = "NORMAL — healthy expansion signal"
                parts.append(f"  Yield Curve (10Y-2Y): {e.yield_curve_spread:+.2f}% [{curve_signal}]")
            if e.vix is not None:
                vix_level = "LOW (<15)" if e.vix < 15 else ("ELEVATED (15-25)" if e.vix < 25 else "HIGH (>25)")
                parts.append(f"  VIX (Fear Gauge): {e.vix:.1f} [{vix_level}]")
            if e.sp500_level is not None:
                parts.append(f"  S&P 500: {e.sp500_level:,.1f}")
                sp_parts = []
                if e.sp500_change_1d_pct is not None:
                    sp_parts.append(f"1D: {e.sp500_change_1d_pct:+.2f}%")
                if e.sp500_change_1m_pct is not None:
                    sp_parts.append(f"1M: {e.sp500_change_1m_pct:+.2f}%")
                if sp_parts:
                    parts.append(f"    Performance: {' | '.join(sp_parts)}")
            if e.dollar_index is not None:
                dollar_note = ""
                if e.dollar_index_change_1m_pct is not None:
                    direction = "strengthening" if e.dollar_index_change_1m_pct > 0 else "weakening"
                    dollar_note = f" ({direction}, 1M: {e.dollar_index_change_1m_pct:+.1f}%)"
                parts.append(f"  Dollar Index (DXY): {e.dollar_index:.1f}{dollar_note}")
            parts.append("")

        # Fear & Greed for market mood
        if data.sentiment and data.sentiment.fear_greed_index is not None:
            parts.append(f"MARKET MOOD: Fear & Greed Index = {data.sentiment.fear_greed_index}/100 ({data.sentiment.fear_greed_label})\n")

        # WORLD NEWS — THE MOST CRITICAL DATA for macro/geopolitical analysis
        if data.sentiment and data.sentiment.world_news_items:
            parts.append(f"WORLD & GEOPOLITICAL NEWS ({len(data.sentiment.world_news_items)} articles — THIS IS YOUR PRIMARY DATA, analyze ALL):")
            for item in data.sentiment.world_news_items[:40]:
                date_str = f" ({item.published_at})" if item.published_at else ""
                source_str = f"[{item.source}]" if item.source else ""
                parts.append(f"  - {source_str}{date_str} {item.title}")
            parts.append("")

        # Stock-specific financial news
        if data.sentiment and data.sentiment.news_items:
            parts.append(f"STOCK-SPECIFIC NEWS ({len(data.sentiment.news_items)} articles — analyze for macro relevance):")
            for item in data.sentiment.news_items[:20]:
                date_str = f" ({item.published_at})" if item.published_at else ""
                parts.append(f"  - [{item.source}]{date_str} {item.title}")
            parts.append("")

        # Twitter — valuable for real-time macro sentiment
        if data.sentiment and data.sentiment.twitter_mention_count > 0:
            s = data.sentiment
            parts.append(f"TWITTER/X MACRO CHATTER ({s.twitter_mention_count} mentions, sentiment: {s.twitter_sentiment:+.3f}):")
            if s.twitter_top_posts:
                for post in s.twitter_top_posts[:10]:
                    parts.append(f"  - {post[:200]}")
            parts.append("")

        return "\n".join(parts)
