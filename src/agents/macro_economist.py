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

        # Company context (needed to connect macro to this specific stock)
        if data.fundamentals:
            f = data.fundamentals
            parts.append(f"COMPANY: {f.company_name}")
            parts.append(f"  Sector: {f.sector} / {f.industry}")
            if f.revenue is not None:
                parts.append(f"  Revenue: ${f.revenue:,.0f}")
            if f.revenue_growth is not None:
                parts.append(f"  Revenue Growth: {f.revenue_growth:.1%}")
            parts.append("")

        if data.price:
            parts.append(f"CURRENT PRICE: ${data.price.current_price:.2f}")
            parts.append(f"  Market Cap: ${data.price.market_cap:,.0f}")
            parts.append(f"  From 52W High: {data.price.from_52w_high_pct:.1f}%\n")

        # Economic data
        if data.economic:
            e = data.economic
            parts.append("MACRO INDICATORS:")
            if e.fed_funds_rate is not None:
                parts.append(f"  Fed Funds Rate: {e.fed_funds_rate:.2f}%")
            if e.cpi_yoy is not None:
                parts.append(f"  CPI (YoY): {e.cpi_yoy:.1f}%")
            if e.gdp_growth is not None:
                parts.append(f"  GDP Growth: {e.gdp_growth:.1f}%")
            if e.unemployment_rate is not None:
                parts.append(f"  Unemployment: {e.unemployment_rate:.1f}%")
            if e.treasury_10y_yield is not None:
                parts.append(f"  10Y Treasury Yield: {e.treasury_10y_yield:.2f}%")
            if e.vix is not None:
                parts.append(f"  VIX (Fear Gauge): {e.vix:.1f}")
            parts.append("")

        # Fear & Greed for market mood
        if data.sentiment and data.sentiment.fear_greed_index is not None:
            parts.append(f"MARKET MOOD: Fear & Greed Index = {data.sentiment.fear_greed_index}/100 ({data.sentiment.fear_greed_label})\n")

        # News (critical for macro/geopolitical context)
        if data.sentiment and data.sentiment.news_items:
            parts.append(f"RECENT NEWS & EVENTS ({len(data.sentiment.news_items)} articles):")
            for item in data.sentiment.news_items[:20]:
                date_str = f" ({item.published_at})" if item.published_at else ""
                parts.append(f"  - [{item.source}]{date_str} {item.title}")
            parts.append("")

        return "\n".join(parts)
