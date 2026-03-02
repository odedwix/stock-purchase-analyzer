"""Trend Forecast Service — identifies emerging investment themes.

Collects global macro data (world news, economic indicators, sector performance,
Twitter sentiment) and uses an LLM to identify 3-5 emerging investment trends
that are forming now but haven't been fully priced in.

Results are cached for 12 hours to minimize API costs (1 call per ~half day).
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from config.settings import PROMPTS_DIR
from src.agents.base_agent import _extract_json
from src.agents.llm_provider import get_provider

logger = logging.getLogger(__name__)

_CACHE_FILE = Path(__file__).parent.parent.parent / "data" / "trend_forecast_cache.json"
_CACHE_TTL_HOURS = 12


def _load_cache() -> dict | None:
    """Load cached forecast if fresh enough."""
    if not _CACHE_FILE.exists():
        return None
    try:
        data = json.loads(_CACHE_FILE.read_text())
        cached_at = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_at < timedelta(hours=_CACHE_TTL_HOURS):
            return data.get("forecast")
    except Exception:
        pass
    return None


def _save_cache(forecast: dict):
    """Save forecast to disk cache."""
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps({
        "cached_at": datetime.now().isoformat(),
        "forecast": forecast,
    }, indent=2))


def _build_context(sector_data: list[dict], market_data=None) -> str:
    """Build context string from collected data for the LLM."""
    parts = ["=== Current Market Data for Trend Analysis ===\n"]
    parts.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # Sector performance
    if sector_data:
        parts.append("TODAY'S SECTOR PERFORMANCE:")
        for s in sector_data:
            parts.append(f"  {s['sector']} ({s['etf']}): {s['change_pct']:+.2f}% "
                         f"— Companies: {', '.join(s['companies'])}")
        parts.append("")

    # Economic / macro data
    if market_data:
        if market_data.economic:
            e = market_data.economic
            parts.append("MACRO INDICATORS:")
            if e.vix is not None:
                parts.append(f"  VIX: {e.vix:.1f}")
            if e.sp500_level is not None:
                parts.append(f"  S&P 500: {e.sp500_level:.2f}")
            if e.treasury_10y_yield is not None:
                parts.append(f"  10Y Treasury: {e.treasury_10y_yield:.2f}%")
            if e.treasury_2y_yield is not None:
                parts.append(f"  2Y Treasury: {e.treasury_2y_yield:.2f}%")
            if e.dollar_index is not None:
                parts.append(f"  Dollar Index: {e.dollar_index:.2f}")
            parts.append("")

        if market_data.sentiment:
            s = market_data.sentiment
            if s.fear_greed_index is not None:
                parts.append(f"MARKET MOOD: Fear & Greed = {s.fear_greed_index}/100 ({s.fear_greed_label})\n")

            if s.world_news_items:
                _news = s.world_news_items[:30]
                parts.append(f"WORLD NEWS (top {len(_news)} of {len(s.world_news_items)} articles):")
                for item in _news:
                    parts.append(f"  - {item.title[:120]}")
                parts.append("")

            if s.twitter_top_posts:
                _tweets = s.twitter_top_posts[:8]
                parts.append(f"TWITTER/X SIGNALS ({s.twitter_mention_count} mentions):")
                for post in _tweets:
                    parts.append(f"  - {post[:120]}")
                parts.append("")

    return "\n".join(parts)


async def generate_trend_forecast(
    sector_data: list[dict],
    market_data=None,
    force_refresh: bool = False,
) -> dict:
    """Generate or return cached trend forecast.

    Args:
        sector_data: List of sector performance dicts from get_sector_performance()
        market_data: Optional StockDataPackage from collect_market_overview()
        force_refresh: If True, bypass cache and regenerate

    Returns:
        Dict with emerging_themes, contrarian_opportunities, market_context
    """
    # Check cache first
    if not force_refresh:
        cached = _load_cache()
        if cached:
            logger.info("Trend forecast loaded from cache")
            return cached

    # Load the prompt
    prompt_path = PROMPTS_DIR / "trend_forecaster.md"
    if not prompt_path.exists():
        return {"error": "Trend forecaster prompt not found"}
    system_prompt = prompt_path.read_text()

    # Build context from all available data
    context = _build_context(sector_data, market_data)

    user_message = (
        "Analyze the current market data, world news, and sector performance below. "
        "Identify 3-5 EMERGING investment themes that are forming NOW but haven't been "
        "fully priced in yet. Also identify 1-2 contrarian opportunities where the market "
        "is overreacting to bad news. Respond ONLY with valid JSON.\n\n"
        f"{context}"
    )

    provider = get_provider("agent")
    try:
        response_text, input_tokens, output_tokens = await provider.generate(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=3000,
            temperature=0.7,
        )
        logger.info(f"Trend forecast generated: {input_tokens} in, {output_tokens} out")

        forecast = _extract_json(response_text)

        # Cache the result
        _save_cache(forecast)

        return forecast
    except Exception as e:
        logger.error(f"Trend forecast generation failed: {e}")
        return {"error": str(e)}
