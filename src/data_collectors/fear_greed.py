import logging
import re
from typing import Any

import httpx

from src.data_collectors.base import BaseCollector

logger = logging.getLogger(__name__)


class FearGreedCollector(BaseCollector):
    """Collects CNN Fear & Greed Index via web scraping. No key needed."""

    def __init__(self):
        from config.settings import settings

        super().__init__(cache_ttl=settings.sentiment_cache_ttl)

    def _cache_key(self, symbol: str) -> str:
        return "FearGreedCollector:global"  # Not per-symbol

    async def _fetch_raw(self, symbol: str) -> Any:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        # Try CNN API first
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                response = await client.get(
                    "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
                    headers=headers,
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.debug(f"CNN Fear & Greed API: {e}")

        # Try alternative-me API (popular free alternative)
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                response = await client.get(
                    "https://api.alternative.me/fng/?limit=1&format=json",
                    headers={"User-Agent": headers["User-Agent"]},
                )
                if response.status_code == 200:
                    data = response.json()
                    if "data" in data and data["data"]:
                        entry = data["data"][0]
                        return {
                            "score": int(entry.get("value", 50)),
                            "label": entry.get("value_classification", "Neutral"),
                            "source": "alternative.me",
                        }
        except Exception as e:
            logger.debug(f"Alternative.me Fear & Greed API: {e}")

        logger.warning("All Fear & Greed sources failed")
        return None

    def _transform(self, symbol: str, raw: Any) -> tuple[int | None, str | None]:
        """Returns (score, label) tuple."""
        if raw is None:
            return None, None

        try:
            # CNN API format
            if "fear_and_greed" in raw:
                score = int(raw["fear_and_greed"]["score"])
                rating = raw["fear_and_greed"].get("rating", "")
                return score, rating

            # Alternative.me or simple format
            if "score" in raw:
                score = int(raw["score"])
                label = raw.get("label") or self._score_to_label(score)
                return score, label

            return None, None
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse Fear & Greed data: {e}")
            return None, None

    @staticmethod
    def _score_to_label(score: int) -> str:
        if score <= 25:
            return "Extreme Fear"
        elif score <= 45:
            return "Fear"
        elif score <= 55:
            return "Neutral"
        elif score <= 75:
            return "Greed"
        else:
            return "Extreme Greed"
