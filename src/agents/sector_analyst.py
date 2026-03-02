import json
import logging
import re
from pathlib import Path

from config.settings import PROMPTS_DIR
from src.agents.base_agent import _extract_json
from src.agents.llm_provider import get_provider
from src.agents.token_budget import TokenBudget
from src.models.stock_data import StockDataPackage

logger = logging.getLogger(__name__)


class SectorAnalystAgent:
    """Analyzes geopolitical events and maps them to sector impacts with ETF/stock recommendations.

    Unlike the other agents that analyze a specific stock, this agent looks at the
    BIG PICTURE: what world events are happening and which sectors/ETFs should you
    invest in across immediate, near-term, and medium-term horizons.
    """

    def __init__(self):
        self.name = "Sector Analyst"
        self.provider = get_provider("agent")
        self.system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        path = PROMPTS_DIR / "sector_analyst.md"
        if path.exists():
            return path.read_text()
        raise FileNotFoundError(f"Prompt file not found: {path}")

    def _format_data(self, data: StockDataPackage) -> str:
        """Format world news, macro data, and market context for sector analysis."""
        parts = [f"=== Sector Impact Analysis Context ===\n"]
        parts.append(f"Stock being analyzed: {data.symbol}\n")

        # Economic context
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
                parts.append(f"  10Y Treasury: {e.treasury_10y_yield:.2f}%")
            if e.vix is not None:
                parts.append(f"  VIX: {e.vix:.1f}")
            parts.append("")

        # Fear & Greed
        if data.sentiment and data.sentiment.fear_greed_index is not None:
            parts.append(f"MARKET MOOD: Fear & Greed = {data.sentiment.fear_greed_index}/100 ({data.sentiment.fear_greed_label})\n")

        # Company context for reference
        if data.fundamentals:
            parts.append(f"REFERENCE COMPANY: {data.fundamentals.company_name} ({data.fundamentals.sector} / {data.fundamentals.industry})\n")

        # WORLD NEWS — the primary data for sector analysis
        if data.sentiment and data.sentiment.world_news_items:
            parts.append(f"WORLD & GEOPOLITICAL NEWS ({len(data.sentiment.world_news_items)} articles — ANALYZE EVERY HEADLINE FOR SECTOR IMPACT):")
            for item in data.sentiment.world_news_items:
                date_str = f" ({item.published_at})" if item.published_at else ""
                source_str = f"[{item.source}]" if item.source else ""
                parts.append(f"  - {source_str}{date_str} {item.title}")
            parts.append("")

        # Stock-specific news for additional context
        if data.sentiment and data.sentiment.news_items:
            parts.append(f"FINANCIAL NEWS ({len(data.sentiment.news_items)} articles):")
            for item in data.sentiment.news_items[:15]:
                date_str = f" ({item.published_at})" if item.published_at else ""
                parts.append(f"  - [{item.source}]{date_str} {item.title}")
            parts.append("")

        # Twitter for real-time signals
        if data.sentiment and data.sentiment.twitter_top_posts:
            parts.append(f"TWITTER/X CHATTER ({data.sentiment.twitter_mention_count} mentions):")
            for post in data.sentiment.twitter_top_posts[:10]:
                parts.append(f"  - {post[:200]}")
            parts.append("")

        return "\n".join(parts)

    async def analyze(self, data: StockDataPackage, budget: TokenBudget) -> dict:
        """Run sector impact analysis and return structured results."""
        await budget.wait_if_needed()

        user_message = (
            f"Analyze the current world events and their impact on market sectors. "
            f"Recommend specific ETFs and stocks for immediate, near-term, and medium-term investment. "
            f"Respond ONLY with valid JSON.\n\n{self._format_data(data)}"
        )

        response_text, input_tokens, output_tokens = await self.provider.generate(
            system_prompt=self.system_prompt,
            user_message=user_message,
            max_tokens=4000,
            temperature=0.7,
        )
        budget.record_usage(input_tokens, output_tokens)

        try:
            parsed = _extract_json(response_text)
            return parsed
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Sector Analyst returned unparseable response: {e}")
            return {
                "error": str(e),
                "raw_reasoning": response_text,
                "sector_impacts": [],
                "top_picks": [],
            }
