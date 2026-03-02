from src.agents.base_agent import BaseAgent
from src.models.stock_data import StockDataPackage


class RiskManagerAgent(BaseAgent):
    """Risk assessment and portfolio protection specialist."""

    def __init__(self, **kwargs):
        super().__init__(
            name="Risk Manager",
            prompt_file="risk_manager.md",
            **kwargs,
        )

    def _format_data(self, data: StockDataPackage) -> str:
        """Risk manager gets ALL data — needs the full picture including world news."""
        parts = [data.to_summary_text()]

        # Expand world news for risk assessment (summary only shows 5)
        if data.sentiment and data.sentiment.world_news_items:
            parts.append(f"\nWORLD & GEOPOLITICAL NEWS — FULL LIST ({len(data.sentiment.world_news_items)} articles, analyze ALL for risk):")
            for item in data.sentiment.world_news_items[:40]:
                date_str = f" ({item.published_at})" if item.published_at else ""
                parts.append(f"  - [{item.source}]{date_str} {item.title}")

        # Expand stock news
        if data.sentiment and data.sentiment.news_items:
            parts.append(f"\nSTOCK NEWS — FULL LIST ({len(data.sentiment.news_items)} articles):")
            for item in data.sentiment.news_items[:25]:
                date_str = f" ({item.published_at})" if item.published_at else ""
                parts.append(f"  - [{item.source}]{date_str} {item.title}")

        # Reddit top posts for risk signals
        if data.sentiment and data.sentiment.reddit_top_posts:
            parts.append(f"\nREDDIT TOP DISCUSSIONS ({len(data.sentiment.reddit_top_posts)} posts):")
            for post in data.sentiment.reddit_top_posts[:10]:
                parts.append(f"  - {post}")

        # Twitter posts for risk signals
        if data.sentiment and data.sentiment.twitter_top_posts:
            parts.append(f"\nTWITTER/X DISCUSSIONS ({len(data.sentiment.twitter_top_posts)} posts):")
            for post in data.sentiment.twitter_top_posts[:10]:
                parts.append(f"  - {post[:200]}")

        return "\n".join(parts)
