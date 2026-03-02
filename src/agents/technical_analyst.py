from src.agents.base_agent import BaseAgent
from src.models.stock_data import StockDataPackage


class TechnicalAnalystAgent(BaseAgent):
    """Chart patterns and technical indicators specialist."""

    def __init__(self, **kwargs):
        super().__init__(
            name="Technical Analyst",
            prompt_file="technical_analyst.md",
            **kwargs,
        )

    def _format_data(self, data: StockDataPackage) -> str:
        """Send comprehensive price action data and technical indicators."""
        parts = [f"=== Technical Data for {data.symbol} ===\n"]

        if data.price:
            p = data.price
            parts.append("CURRENT PRICE ACTION:")
            parts.append(f"  Current: ${p.current_price:.2f}")
            parts.append(f"  Open: ${p.open_price:.2f}")
            parts.append(f"  Day Range: ${p.day_low:.2f} - ${p.day_high:.2f}")
            parts.append(f"  Previous Close: ${p.previous_close:.2f}")
            parts.append(f"  Change Today: {p.price_change_pct:+.2f}%")
            parts.append(f"  52W Range: ${p.week_52_low:.2f} - ${p.week_52_high:.2f}")
            parts.append(f"  From 52W High: {p.from_52w_high_pct:.1f}%")
            parts.append(f"  Volume: {p.volume:,}")
            parts.append(f"  Avg Volume: {p.avg_volume:,}")
            parts.append(f"  Volume vs Avg: {p.volume_vs_avg:.2f}x")

            # Pre-market / After-hours
            if p.pre_market_price:
                parts.append(f"  PRE-MARKET: ${p.pre_market_price:.2f} ({p.pre_market_change_pct:+.2f}%)")
            if p.post_market_price:
                parts.append(f"  AFTER-HOURS: ${p.post_market_price:.2f} ({p.post_market_change_pct:+.2f}%)")

            # Multi-timeframe performance
            parts.append("\nMULTI-TIMEFRAME PERFORMANCE:")
            if p.change_5d_pct is not None:
                parts.append(f"  5-Day: {p.change_5d_pct:+.2f}%")
            if p.change_1m_pct is not None:
                parts.append(f"  1-Month: {p.change_1m_pct:+.2f}%")
            if p.change_3m_pct is not None:
                parts.append(f"  3-Month: {p.change_3m_pct:+.2f}%")
            if p.change_6m_pct is not None:
                parts.append(f"  6-Month: {p.change_6m_pct:+.2f}%")
            if p.change_ytd_pct is not None:
                parts.append(f"  YTD: {p.change_ytd_pct:+.2f}%")

            # Recent daily price history (last 20 days)
            if p.history_dates and p.history_close:
                parts.append(f"\nDAILY PRICE HISTORY (last 20 trading days):")
                recent_dates = p.history_dates[-20:]
                recent_prices = p.history_close[-20:]
                recent_volumes = p.history_volume[-20:] if p.history_volume else []
                for i, (d, price) in enumerate(zip(recent_dates, recent_prices)):
                    vol_str = f"  vol: {recent_volumes[i]:,}" if i < len(recent_volumes) else ""
                    parts.append(f"    {d}: ${price:.2f}{vol_str}")

            # Intraday data (last 5 days hourly)
            if p.intraday_dates and p.intraday_close:
                parts.append(f"\nINTRADAY 5-DAY (hourly, last 24 entries):")
                recent_intraday = list(zip(p.intraday_dates[-24:], p.intraday_close[-24:]))
                for dt, price in recent_intraday:
                    parts.append(f"    {dt}: ${price:.2f}")
            parts.append("")

        if data.technical:
            t = data.technical
            parts.append("TECHNICAL INDICATORS:")

            # Trend
            parts.append("  TREND:")
            if t.sma_20 is not None:
                parts.append(f"    SMA 20: ${t.sma_20:.2f}")
            if t.sma_50 is not None:
                parts.append(f"    SMA 50: ${t.sma_50:.2f}")
            if t.sma_200 is not None:
                parts.append(f"    SMA 200: ${t.sma_200:.2f}")
            if t.ema_12 is not None:
                parts.append(f"    EMA 12: ${t.ema_12:.2f}")
            if t.ema_26 is not None:
                parts.append(f"    EMA 26: ${t.ema_26:.2f}")

            # Price relative to MAs
            if data.price and t.sma_20 and t.sma_50 and t.sma_200:
                price = data.price.current_price
                pct_from_20 = ((price - t.sma_20) / t.sma_20) * 100
                pct_from_50 = ((price - t.sma_50) / t.sma_50) * 100
                pct_from_200 = ((price - t.sma_200) / t.sma_200) * 100
                parts.append(f"    Price vs SMA 20: {pct_from_20:+.1f}%")
                parts.append(f"    Price vs SMA 50: {pct_from_50:+.1f}%")
                parts.append(f"    Price vs SMA 200: {pct_from_200:+.1f}%")
                # MA alignment
                if t.sma_20 > t.sma_50 > t.sma_200:
                    parts.append("    MA Alignment: BULLISH (20 > 50 > 200)")
                elif t.sma_20 < t.sma_50 < t.sma_200:
                    parts.append("    MA Alignment: BEARISH (20 < 50 < 200)")
                else:
                    parts.append("    MA Alignment: MIXED")
                if t.sma_50 > t.sma_200:
                    parts.append("    Golden Cross active (SMA 50 > SMA 200)")
                else:
                    parts.append("    Death Cross active (SMA 50 < SMA 200)")

            # Momentum
            parts.append("  MOMENTUM:")
            if t.rsi_14 is not None:
                status = "OVERBOUGHT" if t.rsi_14 > 70 else ("OVERSOLD" if t.rsi_14 < 30 else "NEUTRAL")
                parts.append(f"    RSI(14): {t.rsi_14:.1f} [{status}]")
            if t.macd is not None:
                macd_dir = "BULLISH" if t.macd > (t.macd_signal or 0) else "BEARISH"
                parts.append(f"    MACD: {t.macd:.3f} (Signal: {t.macd_signal:.3f}) [{macd_dir}]")
                if t.macd_histogram is not None:
                    hist_dir = "expanding" if t.macd_histogram > 0 else "contracting"
                    parts.append(f"    MACD Histogram: {t.macd_histogram:.3f} ({hist_dir})")

            # Bollinger Bands
            parts.append("  VOLATILITY:")
            if t.bollinger_upper is not None and t.bollinger_lower is not None:
                parts.append(f"    Bollinger Upper: ${t.bollinger_upper:.2f}")
                parts.append(f"    Bollinger Lower: ${t.bollinger_lower:.2f}")
                bb_width = t.bollinger_upper - t.bollinger_lower
                parts.append(f"    Bollinger Width: ${bb_width:.2f}")
                if data.price:
                    bb_pct = (data.price.current_price - t.bollinger_lower) / (t.bollinger_upper - t.bollinger_lower) * 100
                    parts.append(f"    Price at {bb_pct:.0f}% of Bollinger range")
            if t.atr_14 is not None:
                parts.append(f"    ATR(14): ${t.atr_14:.2f}")
                if data.price and data.price.current_price > 0:
                    atr_pct = (t.atr_14 / data.price.current_price) * 100
                    parts.append(f"    ATR as % of price: {atr_pct:.1f}%")

            # Support/Resistance
            parts.append("  SUPPORT / RESISTANCE:")
            if t.support_level is not None:
                parts.append(f"    Support: ${t.support_level:.2f}")
                if data.price:
                    dist_support = ((data.price.current_price - t.support_level) / data.price.current_price) * 100
                    parts.append(f"    Distance to support: {dist_support:.1f}%")
            if t.resistance_level is not None:
                parts.append(f"    Resistance: ${t.resistance_level:.2f}")
                if data.price:
                    dist_resist = ((t.resistance_level - data.price.current_price) / data.price.current_price) * 100
                    parts.append(f"    Distance to resistance: {dist_resist:.1f}%")
            parts.append("")

        return "\n".join(parts)
