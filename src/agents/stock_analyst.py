from src.agents.base_agent import BaseAgent
from src.models.stock_data import StockDataPackage


class StockAnalystAgent(BaseAgent):
    """Fundamental analysis specialist."""

    def __init__(self, **kwargs):
        super().__init__(
            name="Stock Analyst",
            prompt_file="stock_analyst.md",
            **kwargs,
        )

    def _format_data(self, data: StockDataPackage) -> str:
        """Send price, fundamentals, and news data for comprehensive fundamental analysis."""
        parts = [f"=== Fundamental Data for {data.symbol} ===\n"]

        if data.price:
            p = data.price
            parts.append(f"PRICE: ${p.current_price:.2f}")
            parts.append(f"  Previous Close: ${p.previous_close:.2f}")
            parts.append(f"  Change Today: {p.price_change_pct:+.2f}%")
            parts.append(f"  52W Range: ${p.week_52_low:.2f} - ${p.week_52_high:.2f}")
            parts.append(f"  From 52W High: {p.from_52w_high_pct:.1f}%")
            parts.append(f"  Market Cap: ${p.market_cap:,.0f}")
            parts.append(f"  Volume vs Avg: {p.volume_vs_avg:.2f}x")

            # Pre-market / After-hours
            if p.pre_market_price:
                parts.append(f"  Pre-Market: ${p.pre_market_price:.2f} ({p.pre_market_change_pct:+.2f}%)")
            if p.post_market_price:
                parts.append(f"  After-Hours: ${p.post_market_price:.2f} ({p.post_market_change_pct:+.2f}%)")

            # Multi-timeframe performance
            timeframes = []
            if p.change_5d_pct is not None:
                timeframes.append(f"5D: {p.change_5d_pct:+.1f}%")
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

        if data.fundamentals:
            f = data.fundamentals
            parts.append(f"COMPANY: {f.company_name} ({f.sector} / {f.industry})")
            for attr, label in [
                ("pe_ratio", "P/E"), ("forward_pe", "Forward P/E"),
                ("peg_ratio", "PEG"), ("price_to_book", "P/B"),
                ("price_to_sales", "P/S"),
            ]:
                val = getattr(f, attr)
                if val is not None:
                    parts.append(f"  {label}: {val:.2f}")

            if f.revenue is not None:
                parts.append(f"  Revenue: ${f.revenue:,.0f}")
            if f.revenue_growth is not None:
                parts.append(f"  Revenue Growth: {f.revenue_growth:.1%}")
            if f.net_income is not None:
                parts.append(f"  Net Income: ${f.net_income:,.0f}")
            if f.profit_margin is not None:
                parts.append(f"  Profit Margin: {f.profit_margin:.1%}")
            if f.operating_margin is not None:
                parts.append(f"  Operating Margin: {f.operating_margin:.1%}")
            if f.return_on_equity is not None:
                parts.append(f"  ROE: {f.return_on_equity:.1%}")
            if f.debt_to_equity is not None:
                parts.append(f"  Debt/Equity: {f.debt_to_equity:.2f}")
            if f.current_ratio is not None:
                parts.append(f"  Current Ratio: {f.current_ratio:.2f}")
            if f.free_cash_flow is not None:
                parts.append(f"  Free Cash Flow: ${f.free_cash_flow:,.0f}")
                if data.price and data.price.market_cap > 0:
                    fcf_yield = (f.free_cash_flow / data.price.market_cap) * 100
                    parts.append(f"  FCF Yield: {fcf_yield:.2f}%")
            if f.total_debt is not None:
                parts.append(f"  Total Debt: ${f.total_debt:,.0f}")
            if f.total_cash is not None:
                parts.append(f"  Total Cash: ${f.total_cash:,.0f}")
            if f.dividend_yield is not None:
                parts.append(f"  Dividend Yield: {f.dividend_yield:.2%}")
            if f.analyst_target_price is not None:
                parts.append(f"  Analyst Target Price: ${f.analyst_target_price:.2f}")
                if data.price:
                    upside = ((f.analyst_target_price - data.price.current_price) / data.price.current_price) * 100
                    parts.append(f"  Analyst Implied Upside: {upside:+.1f}%")
            if f.analyst_recommendation:
                parts.append(f"  Analyst Recommendation: {f.analyst_recommendation}")
            if f.num_analyst_opinions:
                parts.append(f"  Number of Analysts: {f.num_analyst_opinions}")
            parts.append("")

        # News — stock analyst needs to understand how news affects fundamentals
        if data.sentiment and data.sentiment.news_items:
            parts.append(f"RECENT NEWS ({len(data.sentiment.news_items)} articles):")
            for item in data.sentiment.news_items[:25]:
                date_str = f" ({item.published_at})" if item.published_at else ""
                parts.append(f"  - [{item.source}]{date_str} {item.title}")
            parts.append("")

        return "\n".join(parts)
