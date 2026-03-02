import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import quote

import httpx
import yfinance as yf

from config.settings import settings
from src.data_collectors.base import BaseCollector
from src.models.stock_data import FundamentalsData

logger = logging.getLogger(__name__)

# Google News RSS search URL
_GOOGLE_NEWS_SEARCH = (
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
)


class FundamentalsCollector(BaseCollector):
    """Collects fundamental financial data via yfinance."""

    def __init__(self):
        super().__init__(cache_ttl=settings.fundamentals_cache_ttl)

    async def _fetch_raw(self, symbol: str) -> Any:
        loop = asyncio.get_event_loop()
        yf_task = loop.run_in_executor(None, self._fetch_sync, symbol)
        news_task = self._fetch_earnings_news(symbol)
        results = await asyncio.gather(yf_task, news_task, return_exceptions=True)

        yf_data = results[0]
        if isinstance(yf_data, Exception):
            raise yf_data

        earnings_news = results[1] if not isinstance(results[1], Exception) else []
        yf_data["earnings_news"] = earnings_news
        return yf_data

    def _fetch_sync(self, symbol: str) -> dict:
        ticker = yf.Ticker(symbol)
        data = {"info": ticker.info}

        # Fetch next earnings date
        try:
            ed = ticker.earnings_dates
            if ed is not None and not ed.empty:
                future_dates = ed.index[ed.index >= datetime.now()]
                if len(future_dates) > 0:
                    data["next_earnings"] = future_dates[0].strftime("%Y-%m-%d")

                # Also extract past earnings with EPS actual/estimate
                past = ed[ed.index < datetime.now()].head(8)
                if not past.empty:
                    earnings_history = []
                    for date_idx, row in past.iterrows():
                        eps_actual = row.get("Reported EPS")
                        eps_estimate = row.get("EPS Estimate")
                        if eps_actual is not None and eps_estimate is not None:
                            try:
                                actual = float(eps_actual)
                                estimate = float(eps_estimate)
                                surprise = ((actual - estimate) / abs(estimate) * 100) if estimate != 0 else 0
                                quarter_label = date_idx.strftime("%Y-Q") + str((date_idx.month - 1) // 3 + 1)
                                earnings_history.append({
                                    "quarter": quarter_label,
                                    "date": date_idx.strftime("%Y-%m-%d"),
                                    "eps_actual": round(actual, 2),
                                    "eps_estimate": round(estimate, 2),
                                    "surprise_pct": round(surprise, 1),
                                })
                            except (ValueError, TypeError):
                                pass
                    data["earnings_history"] = earnings_history
        except Exception:
            pass

        # Analyst recommendations (upgrades/downgrades)
        try:
            recs = ticker.recommendations
            if recs is not None and not recs.empty:
                data["recommendations"] = recs.tail(15).reset_index().to_dict("records")
        except Exception:
            pass

        # Institutional holders
        try:
            inst = ticker.institutional_holders
            if inst is not None and not inst.empty:
                data["institutional_holders"] = inst.head(10).to_dict("records")
        except Exception:
            pass

        # Dividend history
        try:
            divs = ticker.dividends
            if divs is not None and not divs.empty:
                recent = divs.tail(8)
                annual_total = 0
                try:
                    one_year_ago = datetime.now().timestamp() - 365 * 86400
                    annual_divs = [v for idx, v in divs.items() if idx.timestamp() >= one_year_ago]
                    annual_total = sum(annual_divs) if annual_divs else 0
                except Exception:
                    annual_total = recent.sum() / max(len(recent), 1) * 4

                data["dividend_history"] = {
                    "payment_count": len(divs),
                    "recent_amounts": [round(float(v), 4) for v in recent.values],
                    "annual_total": round(float(annual_total), 4),
                }
        except Exception:
            pass

        # Competitor tickers (same industry)
        try:
            industry_key = data["info"].get("industryKey", "")
            if industry_key:
                industry = yf.Industry(industry_key)
                peers = industry.top_companies
                if peers is not None and not peers.empty:
                    peer_tickers = [t for t in peers.index.tolist()[:6] if t != symbol]
                    data["competitor_tickers"] = peer_tickers[:5]
        except Exception:
            pass

        return data

    async def _fetch_earnings_news(self, symbol: str) -> list[str]:
        """Search Google News RSS for recent earnings call highlights."""
        try:
            ticker = yf.Ticker(symbol)
            company_name = ticker.info.get("longName") or ticker.info.get("shortName") or symbol
            for suffix in [", Inc.", " Inc.", " Corp.", " Corporation", " Ltd.", " Limited", " PLC", " N.V.", " SE"]:
                company_name = company_name.replace(suffix, "")
            company_name = company_name.strip()
        except Exception:
            company_name = symbol

        queries = [
            f'"{company_name}" earnings call',
            f'"{company_name}" quarterly results',
            f'{symbol} earnings beat OR miss',
        ]

        headlines = []
        seen = set()
        async with httpx.AsyncClient(
            timeout=15,
            headers={"User-Agent": "StockAnalyzer/0.1 (educational project)"},
            follow_redirects=True,
        ) as client:
            for query in queries:
                try:
                    url = _GOOGLE_NEWS_SEARCH.format(query=quote(query))
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    articles = self._parse_rss(resp.text)
                    for a in articles[:5]:
                        title = a.get("title", "").strip()
                        if title and title not in seen:
                            seen.add(title)
                            source = a.get("source", "")
                            headlines.append(f"{title} ({source})" if source else title)
                except Exception:
                    pass
                await asyncio.sleep(0.5)

        return headlines[:8]

    @staticmethod
    def _parse_rss(xml_text: str) -> list[dict]:
        """Parse RSS 2.0 XML into article dicts."""
        articles = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return articles

        for item in root.iter("item"):
            title_el = item.find("title")
            source_el = item.find("source")
            title = unescape(title_el.text.strip()) if title_el is not None and title_el.text else ""
            source = source_el.text.strip() if source_el is not None and source_el.text else ""
            if title:
                articles.append({"title": title, "source": source})

        return articles

    def _transform(self, symbol: str, raw: Any) -> FundamentalsData:
        info = raw.get("info", raw) if isinstance(raw, dict) else raw
        next_earnings = raw.get("next_earnings") if isinstance(raw, dict) else None

        # Parse quarterly earnings history
        quarterly_earnings = raw.get("earnings_history", []) if isinstance(raw, dict) else []

        # Parse analyst actions
        analyst_actions = []
        if isinstance(raw, dict) and raw.get("recommendations"):
            for rec in raw["recommendations"]:
                try:
                    date_val = rec.get("Date") or rec.get("date") or rec.get("index", "")
                    if hasattr(date_val, "strftime"):
                        date_str = date_val.strftime("%Y-%m-%d")
                    else:
                        date_str = str(date_val)[:10]
                    firm = rec.get("Firm", "") or rec.get("firm", "")
                    to_grade = rec.get("To Grade", "") or rec.get("toGrade", "")
                    from_grade = rec.get("From Grade", "") or rec.get("fromGrade", "")
                    action = rec.get("Action", "") or rec.get("action", "")

                    if firm and to_grade:
                        entry = f"{date_str}: {firm} -> {to_grade}"
                        if from_grade:
                            entry += f" (from {from_grade})"
                        if action:
                            entry = f"{date_str}: {firm} {action} -> {to_grade}"
                            if from_grade:
                                entry += f" (from {from_grade})"
                        analyst_actions.append(entry)
                except Exception:
                    pass

        # Parse institutional holders
        top_holders = []
        if isinstance(raw, dict) and raw.get("institutional_holders"):
            for holder in raw["institutional_holders"]:
                try:
                    name = holder.get("Holder", "") or holder.get("holder", "")
                    shares = holder.get("Shares", 0) or holder.get("shares", 0)
                    pct = holder.get("% Out", 0) or holder.get("pctHeld", 0)
                    if name:
                        shares_m = int(shares) / 1_000_000 if shares else 0
                        pct_val = float(pct) * 100 if pct and float(pct) < 1 else float(pct or 0)
                        top_holders.append(f"{name}: {pct_val:.1f}% ({shares_m:.0f}M shares)")
                except Exception:
                    pass

        # Parse dividend history
        dividend_summary = ""
        if isinstance(raw, dict) and raw.get("dividend_history"):
            dh = raw["dividend_history"]
            annual = dh.get("annual_total", 0)
            count = dh.get("payment_count", 0)
            if annual > 0:
                dividend_summary = f"${annual:.2f}/year, {count} historical payments"

        # Competitor tickers
        competitors = raw.get("competitor_tickers", []) if isinstance(raw, dict) else []

        # Earnings news
        earnings_news = raw.get("earnings_news", []) if isinstance(raw, dict) else []

        # Business description (truncated to 600 chars)
        biz_desc = info.get("longBusinessSummary", "")
        if len(biz_desc) > 600:
            biz_desc = biz_desc[:597] + "..."

        return FundamentalsData(
            symbol=symbol,
            company_name=info.get("longName", info.get("shortName", "")),
            sector=info.get("sector", ""),
            industry=info.get("industry", ""),
            # Valuation
            pe_ratio=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            peg_ratio=info.get("pegRatio"),
            price_to_book=info.get("priceToBook"),
            price_to_sales=info.get("priceToSalesTrailing12Months"),
            # Profitability
            revenue=info.get("totalRevenue"),
            revenue_growth=info.get("revenueGrowth"),
            net_income=info.get("netIncomeToCommon"),
            profit_margin=info.get("profitMargins"),
            operating_margin=info.get("operatingMargins"),
            return_on_equity=info.get("returnOnEquity"),
            # Balance sheet
            total_debt=info.get("totalDebt"),
            total_cash=info.get("totalCash"),
            debt_to_equity=info.get("debtToEquity"),
            current_ratio=info.get("currentRatio"),
            free_cash_flow=info.get("freeCashflow"),
            # Dividends
            dividend_yield=info.get("dividendYield"),
            # Analyst
            analyst_target_price=info.get("targetMeanPrice"),
            analyst_recommendation=info.get("recommendationKey"),
            num_analyst_opinions=info.get("numberOfAnalystOpinions"),
            # Risk & ownership
            beta=info.get("beta"),
            short_percent_of_float=info.get("shortPercentOfFloat"),
            short_ratio=info.get("shortRatio"),
            shares_outstanding=info.get("sharesOutstanding"),
            held_pct_insiders=info.get("heldPercentInsiders"),
            held_pct_institutions=info.get("heldPercentInstitutions"),
            earnings_date=next_earnings,
            # NEW: Business profile
            business_description=biz_desc,
            full_time_employees=info.get("fullTimeEmployees"),
            # NEW: Quarterly earnings
            quarterly_earnings=quarterly_earnings,
            # NEW: Analyst actions
            analyst_actions=analyst_actions,
            # NEW: Institutional holders
            top_institutional_holders=top_holders,
            # NEW: Dividend history
            dividend_history_summary=dividend_summary,
            # NEW: Competitors
            competitor_tickers=competitors,
            # NEW: Earnings news
            earnings_news=earnings_news,
        )
