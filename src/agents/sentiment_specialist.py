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
        """Only send sentiment-related data: news, reddit, fear & greed, plus price context."""
        parts = [f"=== Sentiment Data for {data.symbol} ===\n"]

        # Basic price context (sentiment needs to know the price action)
        if data.price:
            parts.append(f"CURRENT PRICE: ${data.price.current_price:.2f}")
            parts.append(f"  Change today: {data.price.price_change_pct:+.2f}%")
            parts.append(f"  From 52W High: {data.price.from_52w_high_pct:.1f}%")
            parts.append(f"  Volume vs Avg: {data.price.volume_vs_avg:.2f}x\n")

        # Fear & Greed
        if data.sentiment:
            s = data.sentiment
            if s.fear_greed_index is not None:
                parts.append(f"FEAR & GREED INDEX: {s.fear_greed_index}/100 ({s.fear_greed_label})")
                parts.append("")

            # Reddit
            if s.reddit_mention_count > 0:
                parts.append(f"REDDIT ACTIVITY ({s.reddit_mention_count} mentions this week):")
                parts.append(f"  Overall Sentiment: {s.reddit_sentiment:+.3f} (-1=very bearish, +1=very bullish)")
                if s.reddit_top_posts:
                    parts.append("  Top discussions:")
                    for post in s.reddit_top_posts[:10]:
                        parts.append(f"    - {post}")
                parts.append("")
            else:
                parts.append("REDDIT: No significant mentions found this week\n")

            # News
            if s.news_items:
                parts.append(f"RECENT NEWS ({len(s.news_items)} articles):")
                for item in s.news_items[:20]:
                    date_str = f" ({item.published_at})" if item.published_at else ""
                    parts.append(f"  - [{item.source}]{date_str} {item.title}")
                parts.append("")
            else:
                parts.append("NEWS: No recent articles found\n")

        else:
            parts.append("SENTIMENT DATA: Not available\n")

        return "\n".join(parts)
