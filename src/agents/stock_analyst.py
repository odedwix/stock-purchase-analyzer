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
        """Only send price and fundamentals data."""
        parts = [f"=== Fundamental Data for {data.symbol} ===\n"]

        if data.price:
            parts.append(f"PRICE: ${data.price.current_price:.2f}")
            parts.append(f"  Previous Close: ${data.price.previous_close:.2f}")
            parts.append(f"  Change: {data.price.price_change_pct:+.2f}%")
            parts.append(f"  52W Range: ${data.price.week_52_low:.2f} - ${data.price.week_52_high:.2f}")
            parts.append(f"  From 52W High: {data.price.from_52w_high_pct:.1f}%")
            parts.append(f"  Market Cap: ${data.price.market_cap:,.0f}")
            parts.append(f"  Volume vs Avg: {data.price.volume_vs_avg:.2f}x\n")

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
            if f.dividend_yield is not None:
                parts.append(f"  Dividend Yield: {f.dividend_yield:.2%}")
            if f.analyst_target_price is not None:
                parts.append(f"  Analyst Target Price: ${f.analyst_target_price:.2f}")
            if f.analyst_recommendation:
                parts.append(f"  Analyst Recommendation: {f.analyst_recommendation}")
            if f.num_analyst_opinions:
                parts.append(f"  Number of Analysts: {f.num_analyst_opinions}")

        return "\n".join(parts)
