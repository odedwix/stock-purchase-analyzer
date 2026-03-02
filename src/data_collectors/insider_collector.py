"""Collects insider trading data from SEC EDGAR Form 4 filings. No API key needed."""

import asyncio
import logging
import re
from typing import Any

import httpx

from config.settings import settings
from src.data_collectors.base import BaseCollector

logger = logging.getLogger(__name__)

# SEC requires a User-Agent with contact info
SEC_USER_AGENT = "StockAnalyzer/0.1 (odedgranot@gmail.com)"
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_FULLTEXT_URL = "https://efts.sec.gov/LATEST/search-index"


class InsiderCollector(BaseCollector):
    """Collects insider transaction data from SEC EDGAR Form 4 filings."""

    def __init__(self):
        super().__init__(cache_ttl=86400)  # 24h cache — insider filings are infrequent

    async def _fetch_raw(self, symbol: str) -> Any:
        """Fetch Form 4 filings from SEC EDGAR full-text search."""
        from datetime import datetime, timedelta

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

        headers = {"User-Agent": SEC_USER_AGENT, "Accept": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    "https://efts.sec.gov/LATEST/search-index",
                    params={
                        "q": f'"{symbol}"',
                        "forms": "4",
                        "dateRange": "custom",
                        "startdt": start_date,
                        "enddt": end_date,
                    },
                    headers=headers,
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.debug(f"SEC EDGAR search-index failed for {symbol}: {e}")

        # Fallback: try the standard EDGAR full-text search API
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    "https://efts.sec.gov/LATEST/search-index",
                    params={
                        "q": f'"{symbol}"',
                        "forms": "4",
                    },
                    headers=headers,
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.debug(f"SEC EDGAR fallback also failed for {symbol}: {e}")

        return None

    def _transform(self, symbol: str, raw: Any) -> dict:
        """Parse EDGAR results into insider trading summary.

        Returns a dict to be merged into FundamentalsData fields.
        """
        if not raw:
            return {"insider_buys_90d": 0, "insider_sells_90d": 0, "insider_net_shares": 0, "insider_transactions": []}

        buys = 0
        sells = 0
        transactions = []

        hits = raw.get("hits", raw.get("filings", []))
        if isinstance(hits, dict):
            hits = hits.get("hits", [])

        for hit in hits[:50]:  # Limit to avoid parsing too many
            source = hit.get("_source", hit) if isinstance(hit, dict) else {}
            if isinstance(source, dict):
                # Try to extract transaction type from filing text/title
                title = source.get("display_names", source.get("file_description", ""))
                if isinstance(title, list):
                    title = " ".join(title)
                title = str(title).upper()

                entity = source.get("entity_name", source.get("display_names", "Unknown"))
                if isinstance(entity, list):
                    entity = entity[0] if entity else "Unknown"
                date = source.get("file_date", source.get("period_of_report", ""))

                # Detect buy vs sell from filing content
                if any(kw in title for kw in ["PURCHASE", "ACQUISITION", "BUY", "GRANT"]):
                    buys += 1
                    transactions.append(f"{entity} — purchase ({date})")
                elif any(kw in title for kw in ["SALE", "SOLD", "DISPOSITION", "SELL"]):
                    sells += 1
                    transactions.append(f"{entity} — sale ({date})")
                else:
                    # Count the filing but can't determine direction
                    transactions.append(f"{entity} — Form 4 filed ({date})")

        return {
            "insider_buys_90d": buys,
            "insider_sells_90d": sells,
            "insider_net_shares": buys - sells,
            "insider_transactions": transactions[:10],  # Keep top 10
        }
