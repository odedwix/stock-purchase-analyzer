from src.agents.base_agent import BaseAgent
from src.models.stock_data import StockDataPackage


class SentimentSpecialistAgent(BaseAgent):
    """Social media and crowd psychology specialist."""

    def __init__(self, **kwargs):
        super().__init__(
            name="Sentiment Specialist",
            prompt_file="sentiment_specialist.md",
            **kwargs,
        )

    def _format_data(self, data: StockDataPackage) -> str:
        """Send all sentiment data with rich context."""
        parts = [f"=== Sentiment Data for {data.symbol} ===\n"]

        # Price context with temporal data
        if data.price:
            p = data.price
            parts.append(f"PRICE CONTEXT:")
            parts.append(f"  Current: ${p.current_price:.2f} ({p.price_change_pct:+.2f}% today)")
            parts.append(f"  From 52W High: {p.from_52w_high_pct:.1f}%")
            parts.append(f"  Volume vs Avg: {p.volume_vs_avg:.2f}x")

            if p.pre_market_price:
                parts.append(f"  Pre-Market: ${p.pre_market_price:.2f} ({p.pre_market_change_pct:+.2f}%)")
            if p.post_market_price:
                parts.append(f"  After-Hours: ${p.post_market_price:.2f} ({p.post_market_change_pct:+.2f}%)")

            # Multi-timeframe for context
            timeframes = []
            if p.change_5d_pct is not None:
                timeframes.append(f"5D: {p.change_5d_pct:+.1f}%")
            if p.change_1m_pct is not None:
                timeframes.append(f"1M: {p.change_1m_pct:+.1f}%")
            if p.change_3m_pct is not None:
                timeframes.append(f"3M: {p.change_3m_pct:+.1f}%")
            if timeframes:
                parts.append(f"  Recent Performance: {' | '.join(timeframes)}")
            parts.append("")

        if data.sentiment:
            s = data.sentiment

            # Fear & Greed
            if s.fear_greed_index is not None:
                parts.append(f"FEAR & GREED INDEX: {s.fear_greed_index}/100 ({s.fear_greed_label})")
                if s.fear_greed_index <= 25:
                    parts.append("  >> EXTREME FEAR — historically a contrarian BUY signal")
                elif s.fear_greed_index >= 75:
                    parts.append("  >> EXTREME GREED — historically a contrarian SELL signal")
                parts.append("")

            # Reddit — detailed breakdown
            if s.reddit_mention_count > 0:
                parts.append(f"REDDIT ACTIVITY ({s.reddit_mention_count} mentions this week):")
                parts.append(f"  Overall Sentiment Score: {s.reddit_sentiment:+.3f} (-1=very bearish, +1=very bullish)")
                if s.reddit_bullish_count or s.reddit_bearish_count:
                    total = s.reddit_bullish_count + s.reddit_bearish_count
                    bull_pct = (s.reddit_bullish_count / total * 100) if total > 0 else 0
                    parts.append(f"  Bullish Posts: {s.reddit_bullish_count} ({bull_pct:.0f}%)")
                    parts.append(f"  Bearish Posts: {s.reddit_bearish_count} ({100 - bull_pct:.0f}%)")
                if s.reddit_subreddit_breakdown:
                    breakdown = ", ".join(f"r/{k}: {v}" for k, v in s.reddit_subreddit_breakdown.items())
                    parts.append(f"  Subreddit Breakdown: {breakdown}")
                if s.reddit_top_posts:
                    parts.append("  TOP DISCUSSIONS (analyze each for sentiment):")
                    for post in s.reddit_top_posts[:15]:
                        parts.append(f"    - {post}")
                parts.append("")
            else:
                parts.append("REDDIT: No significant mentions found this week\n")

            # News — with all articles for deep analysis
            if s.news_items:
                parts.append(f"RECENT NEWS ({len(s.news_items)} articles — analyze EACH headline):")
                for item in s.news_items[:30]:
                    date_str = f" ({item.published_at})" if item.published_at else ""
                    parts.append(f"  - [{item.source}]{date_str} {item.title}")
                parts.append("")
            else:
                parts.append("NEWS: No recent articles found\n")

        else:
            parts.append("SENTIMENT DATA: Not available\n")

        return "\n".join(parts)
