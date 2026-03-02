import asyncio
import sys
from pathlib import Path

import streamlit as st

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings

st.set_page_config(
    page_title="Stock Purchase Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for visual appeal
st.markdown("""
<style>
    .stMetric > div {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
    }
    .recommendation-buy { color: #00c853; font-weight: bold; font-size: 1.5em; }
    .recommendation-avoid { color: #ff1744; font-weight: bold; font-size: 1.5em; }
    .recommendation-wait { color: #ff9100; font-weight: bold; font-size: 1.5em; }
    .confidence-high { color: #00c853; }
    .confidence-medium { color: #ff9100; }
    .confidence-low { color: #ff1744; }
    div[data-testid="stSidebar"] {
        background-color: #1a1a2e;
        color: white;
    }
</style>
""", unsafe_allow_html=True)


# Position display labels
_POSITION_LABELS = {
    "STRONG_BUY": "STRONG BUY — Great opportunity",
    "BUY": "BUY — Good entry point",
    "WAIT": "WAIT — Watch for better entry",
    "AVOID": "AVOID — Poor risk/reward",
    "STRONG_AVOID": "STRONG AVOID — Stay away",
}

_POSITION_EMOJI = {
    "STRONG_BUY": "🟢",
    "BUY": "🟢",
    "WAIT": "🟡",
    "AVOID": "🔴",
    "STRONG_AVOID": "🔴",
}


def run_async(coro):
    """Run async code from sync Streamlit context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ── Persistent watchlist ──────────────────────────────
import json

_WATCHLIST_FILE = Path(__file__).parent.parent / "data" / "watchlist.json"


def _load_watchlist() -> list[str]:
    """Load watchlist from disk, falling back to default."""
    if _WATCHLIST_FILE.exists():
        try:
            return json.loads(_WATCHLIST_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return settings.default_watchlist.copy()


def _save_watchlist(wl: list[str]):
    """Persist watchlist to disk."""
    _WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    _WATCHLIST_FILE.write_text(json.dumps(wl))


# Sidebar
with st.sidebar:
    st.title("📊 Stock Analyzer")
    st.markdown("---")

    st.subheader("Watchlist")
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = _load_watchlist()
    watchlist = st.session_state["watchlist"]

    # Add stock input
    new_stock = st.text_input("Add stock ticker:", placeholder="e.g., TSLA")
    if st.button("Add to Watchlist") and new_stock:
        ticker = new_stock.upper().strip()
        if ticker not in watchlist:
            watchlist.append(ticker)
            st.session_state["watchlist"] = watchlist
            _save_watchlist(watchlist)
            st.rerun()

    # Display watchlist
    for i, ticker in enumerate(watchlist):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"**{ticker}**")
        with col2:
            if st.button("✕", key=f"remove_{i}"):
                watchlist.remove(ticker)
                st.session_state["watchlist"] = watchlist
                _save_watchlist(watchlist)
                st.rerun()

    st.markdown("---")

    # LLM Provider toggle
    _provider_options = ["groq", "anthropic"]
    _current = settings.llm_provider if settings.llm_provider in _provider_options else "anthropic"
    _provider_idx = _provider_options.index(_current)
    _provider_labels = {"groq": "Groq (free)", "anthropic": "Anthropic (paid)"}
    selected_provider = st.radio(
        "LLM Provider",
        options=_provider_options,
        index=_provider_idx,
        format_func=lambda x: _provider_labels[x],
        help="Groq: free tier, fast but rate-limited (100K tokens/day). Anthropic: paid API, no rate limits, higher quality (Claude Haiku)",
    )
    if selected_provider != settings.llm_provider:
        settings.llm_provider = selected_provider
        st.rerun()

# ============================================================
# MARKET OVERVIEW (shown at startup)
# ============================================================
st.title("Stock Investment Opportunity Analyzer")
st.markdown("*AI-powered multi-agent analysis — should you BUY, WAIT, or AVOID?*")

# ============================================================
# SECTOR PERFORMANCE — always visible, auto-loads
# ============================================================
if "sector_performance" not in st.session_state:
    from src.data_collectors.sector_performance import get_sector_performance
    with st.spinner("Loading sector performance..."):
        st.session_state["sector_performance"] = get_sector_performance()

_sectors = st.session_state.get("sector_performance", [])
if _sectors:
    st.subheader("Today's Sector Performance")

    # Split into gainers and losers
    _gainers = [s for s in _sectors if s["change_pct"] >= 0]
    _losers = [s for s in _sectors if s["change_pct"] < 0]

    # Display in a sorted grid — 4 columns, each sector is expandable
    _sec_cols = st.columns(4)
    for idx, sec in enumerate(_sectors):
        with _sec_cols[idx % 4]:
            pct = sec["change_pct"]
            color = "green" if pct >= 0 else "red"
            arrow = "▲" if pct >= 0 else "▼"
            with st.expander(
                f"{'📈' if pct >= 0 else '📉'} **{sec['sector']}** ({sec['etf']}) {arrow} {pct:+.2f}%",
                expanded=False,
            ):
                st.caption(f"Companies: {', '.join(sec['companies'])}")

                # Load stock details on expand
                _detail_key = f"sector_detail_{sec['etf']}"
                if st.button(f"Show stocks", key=f"load_{sec['etf']}"):
                    from src.data_collectors.sector_performance import get_sector_stock_details
                    with st.spinner("Loading..."):
                        st.session_state[_detail_key] = get_sector_stock_details(sec["companies"])

                if _detail_key in st.session_state:
                    _stocks = st.session_state[_detail_key]
                    for stk in _stocks:
                        _sig_emoji = {"attractive": "🟢", "interesting": "🟡", "neutral": "⚪"}.get(stk["signal"], "⚪")
                        _chg_color = "green" if stk["change_pct"] >= 0 else "red"
                        _name = stk.get("name", stk["ticker"])
                        st.markdown(
                            f"{_sig_emoji} **{stk['ticker']}** ({_name}) ${stk['price']:.2f} "
                            f"<span style='color:{_chg_color}'>{stk['change_pct']:+.2f}%</span>",
                            unsafe_allow_html=True,
                        )
                        _details_parts = []
                        if stk["pe_ratio"]:
                            _details_parts.append(f"<span title='Price-to-Earnings ratio. Under 15 = cheap, over 25 = expensive'>P/E: {stk['pe_ratio']}</span>")
                        if stk["forward_pe"]:
                            _details_parts.append(f"<span title='Forward P/E uses expected future earnings. Lower than trailing P/E = growth expected'>Fwd P/E: {stk['forward_pe']}</span>")
                        _details_parts.append(f"<span title='How far below the 52-week high. Large drops may be a buying opportunity or a warning sign'>vs 52W high: {stk['from_52w_high_pct']:+.1f}%</span>")
                        if stk["market_cap_b"]:
                            _details_parts.append(f"<span title='Market capitalization in billions. Mega >$200B, Large >$10B, Mid >$2B'>${stk['market_cap_b']:.0f}B</span>")
                        st.markdown(f"<span style='font-size:0.85em;color:gray;'>{' | '.join(_details_parts)}</span>", unsafe_allow_html=True)
                        if stk["signal_reasons"]:
                            st.caption(f"→ {', '.join(stk['signal_reasons'])}")

    # Summary line
    _up_count = len(_gainers)
    _down_count = len(_losers)
    if _gainers:
        _best = _gainers[0]
        _best_str = f"Best: **{_best['sector']}** ({_best['etf']}) {_best['change_pct']:+.2f}%"
    else:
        _best_str = ""
    if _losers:
        _worst = _losers[-1]
        _worst_str = f"Worst: **{_worst['sector']}** ({_worst['etf']}) {_worst['change_pct']:+.2f}%"
    else:
        _worst_str = ""

    _summary_parts = [f"{_up_count} sectors up, {_down_count} down"]
    if _best_str:
        _summary_parts.append(_best_str)
    if _worst_str:
        _summary_parts.append(_worst_str)
    st.caption(" | ".join(_summary_parts))

    # Refresh button
    _sec_ref_col, _sec_spacer = st.columns([1, 5])
    with _sec_ref_col:
        if st.button("🔄 Refresh Sectors", key="refresh_sectors"):
            # Clear all sector detail caches too
            for key in list(st.session_state.keys()):
                if key.startswith("sector_detail_"):
                    del st.session_state[key]
            del st.session_state["sector_performance"]
            st.rerun()

st.markdown("---")

# ============================================================
# EMERGING OPPORTUNITIES — AI trend forecasting
# ============================================================
_trend_col1, _trend_col2 = st.columns([3, 1])
with _trend_col2:
    _trend_btn = st.button("Identify Emerging Trends", use_container_width=True)
with _trend_col1:
    if "trend_forecast" in st.session_state:
        _fc = st.session_state["trend_forecast"]
        if _fc and not _fc.get("error"):
            st.caption("Trend forecast loaded ✓")

if _trend_btn:
    with st.spinner("Analyzing global trends and identifying emerging opportunities... (uses 1 API call, cached for 12h)"):
        from src.services.trend_forecast_service import generate_trend_forecast
        # Collect market data if not already loaded
        _market_pkg = None
        if "market_overview" in st.session_state:
            overview = st.session_state["market_overview"]
            # Build a minimal package from existing overview
            _market_pkg = type("Pkg", (), {
                "economic": overview.get("economic"),
                "sentiment": overview.get("sentiment"),
            })()
        else:
            # Collect fresh global data for the forecast
            from src.data_collectors.aggregator import DataAggregator as _TFA
            _tf_agg = _TFA()
            _market_pkg = run_async(_tf_agg.collect_market_overview())

        st.session_state["trend_forecast"] = run_async(
            generate_trend_forecast(
                sector_data=st.session_state.get("sector_performance", []),
                market_data=_market_pkg,
            )
        )
    st.rerun()

if "trend_forecast" in st.session_state:
    _forecast = st.session_state["trend_forecast"]
    if _forecast and not _forecast.get("error"):
        st.subheader("Emerging Investment Opportunities")

        # Market context
        _mkt_ctx = _forecast.get("market_context", "")
        if _mkt_ctx:
            st.info(_mkt_ctx)

        # Emerging themes
        _themes = _forecast.get("emerging_themes", [])
        for _theme in _themes:
            _conf = _theme.get("confidence", "medium")
            _conf_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(_conf, "⚪")
            _timeline = _theme.get("timeline", "")

            with st.expander(
                f"{_conf_emoji} **{_theme.get('theme', '?')}** — {_timeline}",
                expanded=True,
            ):
                st.markdown(_theme.get("thesis", ""))

                # Evidence
                _evidence = _theme.get("evidence", [])
                if _evidence:
                    st.markdown("**Supporting evidence:**")
                    for _ev in _evidence:
                        st.markdown(f"- {_ev}")

                # Why still early
                _early = _theme.get("why_still_early", "")
                if _early:
                    st.success(f"**Why it's still early:** {_early}")

                # Stocks & ETFs to watch
                _stk_col, _etf_col = st.columns(2)
                with _stk_col:
                    _stocks = _theme.get("stocks_to_watch", [])
                    if _stocks:
                        st.markdown("**Stocks to Watch:**")
                        for _s in _stocks:
                            st.markdown(f"- **{_s.get('ticker', '?')}** ({_s.get('name', '')}) — {_s.get('why', '')}")
                with _etf_col:
                    _etfs = _theme.get("etfs_to_watch", [])
                    if _etfs:
                        st.markdown("**ETFs to Watch:**")
                        for _e in _etfs:
                            st.markdown(f"- **{_e.get('ticker', '?')}** ({_e.get('name', '')}) — {_e.get('why', '')}")

                # Sectors
                _sectors_list = _theme.get("sectors", [])
                if _sectors_list:
                    st.caption(f"Sectors: {', '.join(_sectors_list)}")

                # Risks
                _risks = _theme.get("risk_factors", [])
                if _risks:
                    st.warning(f"**Risks:** {' | '.join(_risks)}")

                _inval = _theme.get("invalidation", "")
                if _inval:
                    st.caption(f"Thesis invalidated if: {_inval}")

        # Contrarian opportunities
        _contrarian = _forecast.get("contrarian_opportunities", [])
        if _contrarian:
            st.subheader("Contrarian Opportunities")
            st.caption("Beaten-down sectors/stocks where the market may be overreacting")
            for _c in _contrarian:
                with st.expander(f"**{_c.get('sector_or_stock', '?')}** — {_c.get('timeline', '')}"):
                    st.markdown(f"**Why beaten down:** {_c.get('why_beaten_down', '')}")
                    st.success(f"**Why it's an opportunity:** {_c.get('why_opportunity', '')}")
                    _tickers = _c.get("tickers", [])
                    if _tickers:
                        st.markdown(f"**Tickers:** {', '.join(_tickers)}")

        # Refresh option
        _tf_ref_col, _tf_spacer = st.columns([1, 5])
        with _tf_ref_col:
            if st.button("Refresh Forecast", key="refresh_trends"):
                from src.services.trend_forecast_service import generate_trend_forecast
                _market_pkg = None
                if "market_overview" in st.session_state:
                    overview = st.session_state["market_overview"]
                    _market_pkg = type("Pkg", (), {
                        "economic": overview.get("economic"),
                        "sentiment": overview.get("sentiment"),
                    })()
                with st.spinner("Regenerating forecast..."):
                    st.session_state["trend_forecast"] = run_async(
                        generate_trend_forecast(
                            sector_data=st.session_state.get("sector_performance", []),
                            market_data=_market_pkg,
                            force_refresh=True,
                        )
                    )
                st.rerun()

    elif _forecast and _forecast.get("error"):
        st.error(f"Forecast failed: {_forecast['error']}")

st.markdown("---")

# Market overview section (deeper analysis — on demand)
_market_col1, _market_col2 = st.columns([3, 1])
with _market_col2:
    load_market = st.button("🌍 Deep Market Analysis", use_container_width=True)
with _market_col1:
    if "market_overview" in st.session_state:
        st.caption("Market analysis loaded ✓")

if load_market:
    with st.spinner("Loading deep market analysis & sector outlook..."):
        from src.services.market_overview_service import MarketOverviewService
        service = MarketOverviewService()
        overview = run_async(service.get_market_overview())
        st.session_state["market_overview"] = overview

        # Save snapshot to database
        from src.db.analysis_repo import save_market_snapshot
        eco = overview.get("economic")
        sent = overview.get("sentiment")
        run_async(save_market_snapshot(
            vix=eco.vix if eco else None,
            sp500=eco.sp500_level if eco else None,
            fear_greed=sent.fear_greed_index if sent else None,
            sector_analysis=overview.get("sector_analysis"),
        ))
    st.rerun()

if "market_overview" in st.session_state:
    overview = st.session_state["market_overview"]
    eco = overview.get("economic")
    sent = overview.get("sentiment")

    # Row 1: Key metrics
    if eco:
        m_cols = st.columns(6)
        with m_cols[0]:
            if eco.vix is not None:
                vix_label = "Low" if eco.vix < 15 else ("Elevated" if eco.vix < 25 else "HIGH")
                st.metric("VIX", f"{eco.vix:.1f}", delta=vix_label,
                          delta_color="normal" if eco.vix < 20 else ("off" if eco.vix < 30 else "inverse"),
                          help="Volatility Index (fear gauge). Under 15 = calm/complacent. 15-25 = normal. Over 25 = fearful. Over 30 = panic. High VIX often signals buying opportunities")
        with m_cols[1]:
            if eco.sp500_level is not None:
                st.metric("S&P 500", f"{eco.sp500_level:,.0f}",
                          delta=f"{eco.sp500_change_1d_pct:+.2f}%" if eco.sp500_change_1d_pct else None,
                          help="The S&P 500 index tracks 500 largest US companies. THE benchmark for the US stock market. Daily change shows overall market direction")
        with m_cols[2]:
            if sent and sent.fear_greed_index is not None:
                st.metric("Fear & Greed", f"{sent.fear_greed_index}/100",
                          delta=sent.fear_greed_label,
                          help="CNN Fear & Greed Index (0-100). Under 25 = Extreme Fear (buy signal). Over 75 = Extreme Greed (caution). Contrarian indicator — be greedy when others are fearful")
        with m_cols[3]:
            if eco.treasury_10y_yield is not None:
                st.metric("10Y Treasury", f"{eco.treasury_10y_yield:.2f}%",
                          help="10-Year US Treasury yield. The risk-free rate benchmark. Rising yields = tighter financial conditions, bad for growth stocks. Falling yields = easier money, good for stocks")
        with m_cols[4]:
            if eco.yield_curve_spread is not None:
                yc_label = "INVERTED" if eco.yield_curve_spread < 0 else "Normal"
                st.metric("Yield Curve", f"{eco.yield_curve_spread:+.2f}%", delta=yc_label,
                          delta_color="inverse" if eco.yield_curve_spread < 0 else "normal",
                          help="Spread between 10Y and 2Y Treasury yields. INVERTED (negative) = historically predicts recession within 12-18 months. Normal (positive) = healthy economy")
        with m_cols[5]:
            if eco.dollar_index is not None:
                st.metric("Dollar Index", f"{eco.dollar_index:.1f}",
                          delta=f"{eco.dollar_index_change_1m_pct:+.1f}% 1M" if eco.dollar_index_change_1m_pct else None,
                          help="US Dollar Index (DXY) measures the dollar vs major currencies. Strong dollar hurts US exporters and emerging markets. Weak dollar boosts commodities and multinationals")

    # Row 2: Market interpretation
    if eco and sent:
        vix_val = eco.vix or 20
        fg_val = sent.fear_greed_index or 50
        if vix_val > 25 and fg_val < 30:
            st.info("📉 **Market is in FEAR mode** — historically good time to buy quality stocks at a discount")
        elif vix_val < 15 and fg_val > 70:
            st.warning("📈 **Market is GREEDY and complacent** — be cautious with new positions")
        elif vix_val > 30:
            st.error("🔴 **VIX is very elevated** — high uncertainty, consider smaller position sizes")

    # Row 3: AI Sector outlook
    sector_data = overview.get("sector_analysis", {})
    if sector_data and not sector_data.get("error"):
        sector_impacts = sector_data.get("sector_impacts", [])
        if sector_impacts:
            st.subheader("AI Sector Outlook")
            s_cols = st.columns(4)
            for idx, sector in enumerate(sector_impacts):
                with s_cols[idx % 4]:
                    direction = sector.get("impact_direction", "neutral")
                    dir_emoji = {"positive": "📈", "negative": "📉", "neutral": "➡️"}.get(direction, "")
                    magnitude = sector.get("impact_magnitude", "")
                    st.markdown(f"{dir_emoji} **{sector.get('sector', '?')}** ({magnitude})")

        # Top picks
        top_picks = sector_data.get("top_picks", [])
        if top_picks:
            st.subheader("Top Sector Picks")
            pick_cols = st.columns(min(len(top_picks), 4))
            for i, pick in enumerate(top_picks[:4]):
                with pick_cols[i]:
                    risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(pick.get("risk_level", ""), "⚪")
                    st.metric(pick.get("ticker", "?"), f"+{pick.get('expected_return_pct', 0):.0f}%",
                              help="AI-identified sector pick based on world events and macro analysis. Expected return percentage over the recommended timeframe")
                    st.caption(f"{risk_emoji} {pick.get('timeframe', '')} | {pick.get('rationale', '')[:80]}")

        # Sectors to avoid
        avoid = sector_data.get("sectors_to_avoid", [])
        if avoid:
            st.warning(f"**Sectors to Avoid:** {', '.join(avoid)}")

    st.markdown("---")

# Stock selection
selected_stock = st.selectbox(
    "Select a stock to analyze:",
    options=watchlist,
    index=0 if watchlist else None,
)

if selected_stock:
    # ============================================================
    # QUICK LOOK — Extensive Fundamentals + Charts (no LLM)
    # ============================================================
    import pandas as pd
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    ql_key = f"quicklook_{selected_stock}"
    if ql_key not in st.session_state:
        from src.data_collectors.aggregator import DataAggregator as _QLA
        with st.spinner(f"Loading {selected_stock} fundamentals & charts..."):
            _ql_agg = _QLA()
            st.session_state[ql_key] = run_async(_ql_agg.collect_quick_look(selected_stock))

    ql = st.session_state[ql_key]

    # ── Price Header ─────────────────────────────────
    if ql.price:
        p = ql.price
        _company_name = ""
        if ql.fundamentals and ql.fundamentals.company_name:
            _company_name = f" — {ql.fundamentals.company_name}"
        st.subheader(f"{selected_stock}{_company_name}")

        # Row 1: Price + daily change + volume + market cap
        _ph_cols = st.columns([2, 1, 1, 1, 1, 1, 1])
        with _ph_cols[0]:
            st.metric("Price", f"${p.current_price:.2f}", delta=f"{p.price_change_pct:+.2f}%",
                      help="Current trading price and daily change from previous close")
        with _ph_cols[1]:
            st.metric("Open", f"${p.open_price:.2f}",
                      help="The price at which the stock started trading today")
        with _ph_cols[2]:
            st.metric("Day Range", f"${p.day_low:.2f}–{p.day_high:.2f}",
                      help="The lowest and highest prices the stock traded at today")
        with _ph_cols[3]:
            _vol_str = f"{p.volume/1e6:.1f}M" if p.volume >= 1e6 else f"{p.volume/1e3:.0f}K"
            _vol_ratio = p.volume / p.avg_volume if p.avg_volume > 0 else 1.0
            _vol_delta = f"{_vol_ratio:.1f}x avg" if abs(_vol_ratio - 1.0) > 0.1 else "avg"
            st.metric("Volume", _vol_str, delta=_vol_delta, delta_color="off",
                      help="Number of shares traded today vs the average daily volume. High volume on price moves signals strong conviction")
        with _ph_cols[4]:
            _mcap = p.market_cap
            _mcap_str = f"${_mcap/1e12:.2f}T" if _mcap >= 1e12 else f"${_mcap/1e9:.1f}B" if _mcap >= 1e9 else f"${_mcap/1e6:.0f}M"
            st.metric("Market Cap", _mcap_str,
                      help="Total value of all outstanding shares. Mega-cap >$200B, Large >$10B, Mid >$2B, Small <$2B")
        with _ph_cols[5]:
            st.metric("52W Low", f"${p.week_52_low:.2f}",
                      help="Lowest price in the past 52 weeks. Stocks near their 52W low may be undervalued or in trouble")
        with _ph_cols[6]:
            st.metric("52W High", f"${p.week_52_high:.2f}",
                      help="Highest price in the past 52 weeks. Stocks near their 52W high show strong momentum")

        # Pre/Post market if available
        if p.pre_market_price or p.post_market_price:
            _pm_cols = st.columns(4)
            with _pm_cols[0]:
                if p.pre_market_price:
                    st.metric("Pre-Market", f"${p.pre_market_price:.2f}",
                              delta=f"{p.pre_market_change_pct:+.2f}%" if p.pre_market_change_pct else None,
                              help="Pre-market trading price (4:00-9:30 AM ET). Large pre-market moves often signal important news or earnings. Volume is lower so prices can be volatile")
            with _pm_cols[1]:
                if p.post_market_price:
                    st.metric("After-Hours", f"${p.post_market_price:.2f}",
                              delta=f"{p.post_market_change_pct:+.2f}%" if p.post_market_change_pct else None,
                              help="After-hours trading price (4:00-8:00 PM ET). Earnings reports often move stocks significantly after hours. Lower volume means wider spreads")

        # Row 2: Multi-timeframe performance
        _tf_cols = st.columns(6)
        _timeframes = [
            ("5D", p.change_5d_pct, "Price change over the last 5 trading days"),
            ("1M", p.change_1m_pct, "Price change over the last month (~21 trading days)"),
            ("3M", p.change_3m_pct, "Price change over the last 3 months. Shows medium-term trend"),
            ("6M", p.change_6m_pct, "Price change over the last 6 months. Shows longer-term direction"),
            ("YTD", p.change_ytd_pct, "Year-to-date performance since January 1st"),
            ("From 52W High", p.from_52w_high_pct, "How far below the 52-week high. A large drop may signal a buying opportunity or fundamental problems"),
        ]
        for i, (label, val, tip) in enumerate(_timeframes):
            with _tf_cols[i]:
                if val is not None:
                    st.metric(label, f"{val:+.1f}%", help=tip)

        # 52W range progress bar
        if p.week_52_high > p.week_52_low:
            _range_pct = (p.current_price - p.week_52_low) / (p.week_52_high - p.week_52_low)
            st.markdown(f"<span title='Shows where the current price sits within the 52-week range. Near 0% = near yearly low (potential value). Near 100% = near yearly high (strong momentum or expensive).'>52-Week Range Position: {_range_pct:.0%}</span>", unsafe_allow_html=True)
            st.progress(min(max(_range_pct, 0), 1.0))

        # ── Price Chart with Volume ──────────────────
        if p.history_dates and p.history_close:
            _chart_tab1, _chart_tab2 = st.tabs(["1 Year Chart", "5-Day Intraday"])

            with _chart_tab1:
                _fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                     row_heights=[0.7, 0.3], vertical_spacing=0.05)
                # Price line
                _fig.add_trace(go.Scatter(
                    x=p.history_dates, y=p.history_close, name="Price",
                    line=dict(color="#2196F3", width=2), fill="tozeroy",
                    fillcolor="rgba(33,150,243,0.1)",
                ), row=1, col=1)
                # Moving averages from technical data
                if ql.technical:
                    t = ql.technical
                    if t.sma_50 and len(p.history_dates) >= 50:
                        _fig.add_hline(y=t.sma_50, line_dash="dash", line_color="orange",
                                       annotation_text="SMA 50", row=1, col=1)
                    if t.sma_200 and len(p.history_dates) >= 200:
                        _fig.add_hline(y=t.sma_200, line_dash="dash", line_color="red",
                                       annotation_text="SMA 200", row=1, col=1)
                    if t.support_level:
                        _fig.add_hline(y=t.support_level, line_dash="dot", line_color="green",
                                       annotation_text="Support", row=1, col=1)
                    if t.resistance_level:
                        _fig.add_hline(y=t.resistance_level, line_dash="dot", line_color="red",
                                       annotation_text="Resistance", row=1, col=1)
                # Volume bars
                if p.history_volume:
                    _vol_colors = []
                    for j in range(len(p.history_close)):
                        if j == 0:
                            _vol_colors.append("rgba(128,128,128,0.5)")
                        elif p.history_close[j] >= p.history_close[j-1]:
                            _vol_colors.append("rgba(0,150,0,0.5)")
                        else:
                            _vol_colors.append("rgba(200,0,0,0.5)")
                    _fig.add_trace(go.Bar(
                        x=p.history_dates, y=p.history_volume, name="Volume",
                        marker_color=_vol_colors, showlegend=False,
                    ), row=2, col=1)
                _fig.update_layout(height=450, margin=dict(l=0, r=0, t=10, b=0),
                                   xaxis2_title="Date", yaxis_title="Price ($)",
                                   yaxis2_title="Volume", showlegend=False,
                                   hovermode="x unified")
                st.plotly_chart(_fig, use_container_width=True)

            with _chart_tab2:
                if p.intraday_dates and p.intraday_close:
                    _fig2 = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                          row_heights=[0.7, 0.3], vertical_spacing=0.05)
                    _fig2.add_trace(go.Scatter(
                        x=p.intraday_dates, y=p.intraday_close, name="Price",
                        line=dict(color="#2196F3", width=2), fill="tozeroy",
                        fillcolor="rgba(33,150,243,0.1)",
                    ), row=1, col=1)
                    if p.intraday_volume:
                        _fig2.add_trace(go.Bar(
                            x=p.intraday_dates, y=p.intraday_volume, name="Volume",
                            marker_color="rgba(128,128,128,0.5)", showlegend=False,
                        ), row=2, col=1)
                    _fig2.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=0),
                                        yaxis_title="Price ($)", yaxis2_title="Volume",
                                        showlegend=False, hovermode="x unified")
                    st.plotly_chart(_fig2, use_container_width=True)
                else:
                    st.info("Intraday data not available.")

    # ── Technical Indicators ─────────────────────────
    if ql.technical:
        t = ql.technical
        with st.expander("Technical Indicators", expanded=True):
            _t_col1, _t_col2, _t_col3 = st.columns(3)

            with _t_col1:
                st.markdown("<span title='Momentum indicators measure the speed and strength of price movements. They help identify when a stock is overbought (due for a pullback) or oversold (due for a bounce).'>**Momentum**</span>", unsafe_allow_html=True)
                if t.rsi_14 is not None:
                    _rsi_color = "red" if t.rsi_14 > 70 else "green" if t.rsi_14 < 30 else "gray"
                    _rsi_label = "OVERBOUGHT" if t.rsi_14 > 70 else "OVERSOLD" if t.rsi_14 < 30 else "Neutral"
                    st.markdown(f"<span title='Relative Strength Index: measures if a stock is overbought (>70, likely to drop) or oversold (<30, likely to bounce). Range 0-100.'>"
                                f"RSI (14): <span style='color:{_rsi_color};font-weight:bold'>"
                                f"{t.rsi_14:.1f}</span> — {_rsi_label}</span>", unsafe_allow_html=True)
                    st.markdown(f"<span title='RSI gauge: 0-30 = oversold (bullish), 30-70 = neutral, 70-100 = overbought (bearish). Extreme readings often precede reversals.'>RSI: {t.rsi_14:.0f}/100</span>", unsafe_allow_html=True)
                    st.progress(min(t.rsi_14 / 100, 1.0))
                if t.macd is not None and t.macd_signal is not None:
                    _macd_bullish = t.macd > t.macd_signal
                    _macd_color = "green" if _macd_bullish else "red"
                    _macd_label = "Bullish crossover" if _macd_bullish else "Bearish crossover"
                    st.markdown(f"<span title='MACD (Moving Average Convergence Divergence): when MACD crosses above Signal line, it is a bullish signal (good time to buy). When it crosses below, bearish signal.'>"
                                f"MACD: <span style='color:{_macd_color}'>{t.macd:.2f}</span> "
                                f"(Signal: {t.macd_signal:.2f})</span>", unsafe_allow_html=True)
                    st.markdown(f"<span title='Bullish crossover = MACD above signal line (buy signal). Bearish crossover = MACD below signal line (sell signal). More reliable on daily/weekly timeframes.' style='font-size:0.85em;color:gray;'>{_macd_label}</span>", unsafe_allow_html=True)

            with _t_col2:
                st.markdown("<span title='Moving averages smooth out price data. When price is ABOVE a moving average, the trend is bullish. When below, bearish. Longer periods (200) show major trends.'>**Moving Averages**</span>", unsafe_allow_html=True)
                if ql.price:
                    _cp = ql.price.current_price
                    _ma_items = [
                        ("SMA 20", t.sma_20, "Simple Moving Average over 20 days. Short-term trend. Price above = short-term bullish"),
                        ("SMA 50", t.sma_50, "Simple Moving Average over 50 days. Medium-term trend. Institutional investors watch this closely"),
                        ("SMA 200", t.sma_200, "Simple Moving Average over 200 days. THE key long-term trend indicator. Price above = long-term uptrend"),
                        ("EMA 12", t.ema_12, "Exponential Moving Average (12-day). Reacts faster to recent prices. Used in MACD calculation"),
                        ("EMA 26", t.ema_26, "Exponential Moving Average (26-day). Slower EMA used in MACD. Crossover with EMA12 generates signals"),
                    ]
                    for _ma_name, _ma_val, _ma_tip in _ma_items:
                        if _ma_val:
                            _above = _cp > _ma_val
                            _ma_emoji = "above" if _above else "below"
                            _ma_c = "green" if _above else "red"
                            st.markdown(f"<span title='{_ma_tip}'>{_ma_name}: ${_ma_val:.2f} — "
                                        f"<span style='color:{_ma_c}'>{_ma_emoji}</span></span>",
                                        unsafe_allow_html=True)
                    # Golden/Death cross
                    if t.sma_50 and t.sma_200:
                        if t.sma_50 > t.sma_200:
                            st.success("Golden Cross (SMA50 > SMA200)", icon="✅")
                            st.caption("50-day average is above 200-day — long-term bullish signal")
                        else:
                            st.warning("Death Cross (SMA50 < SMA200)", icon="⚠️")
                            st.caption("50-day average is below 200-day — long-term bearish signal")

            with _t_col3:
                st.markdown("<span title='Volatility measures how much the price swings. Support and resistance are key price levels where buying/selling pressure concentrates.'>**Volatility & Levels**</span>", unsafe_allow_html=True)
                if t.bollinger_upper and t.bollinger_lower and ql.price:
                    _cp = ql.price.current_price
                    _bb_range = t.bollinger_upper - t.bollinger_lower
                    _bb_pos = (_cp - t.bollinger_lower) / _bb_range if _bb_range > 0 else 0.5
                    st.markdown(f"<span title='Bollinger Bands: price typically stays within these bands. Near the top = potentially overbought. Near the bottom = potentially oversold. A breakout above/below can signal a big move.'>"
                                f"Bollinger: ${t.bollinger_lower:.2f} — ${t.bollinger_upper:.2f}</span>", unsafe_allow_html=True)
                    st.markdown(f"<span title='Position within Bollinger Bands. Near 0% = at lower band (oversold, potential bounce). Near 100% = at upper band (overbought, potential pullback). 50% = middle of the range.'>Band position: {_bb_pos:.0%}</span>", unsafe_allow_html=True)
                    st.progress(min(max(_bb_pos, 0), 1.0))
                if t.atr_14 is not None:
                    st.markdown(f"<span title='Average True Range: measures daily price volatility in dollar terms. Higher ATR = more volatile stock. Useful for setting stop-loss levels.'>"
                                f"ATR (14): ${t.atr_14:.2f}</span>", unsafe_allow_html=True)
                    if ql.price:
                        _atr_pct = (t.atr_14 / ql.price.current_price) * 100
                        st.markdown(f"<span title='ATR as percentage of stock price. Under 2% = low volatility. Over 5% = very volatile. Use this to set appropriate stop-loss distances.' style='font-size:0.85em;color:gray;'>Daily volatility: {_atr_pct:.1f}%</span>", unsafe_allow_html=True)
                if t.support_level:
                    st.markdown(f"<span title='Support level: a price floor where buying pressure tends to prevent further decline. Good entry point if the stock bounces off support.'>"
                                f"Support: ${t.support_level:.2f}</span>", unsafe_allow_html=True)
                if t.resistance_level:
                    st.markdown(f"<span title='Resistance level: a price ceiling where selling pressure tends to prevent further rise. A breakout above resistance is a bullish signal.'>"
                                f"Resistance: ${t.resistance_level:.2f}</span>", unsafe_allow_html=True)

    # ── Fundamentals ─────────────────────────────────
    if ql.fundamentals:
        f = ql.fundamentals
        _sector_str = f" — {f.sector}" if f.sector else ""
        _industry_str = f" / {f.industry}" if f.industry else ""
        with st.expander(f"Fundamentals{_sector_str}{_industry_str}", expanded=True):

            # ── Valuation metrics with visual gauges ──
            st.markdown("##### Valuation")
            _v_col1, _v_col2, _v_col3, _v_col4, _v_col5 = st.columns(5)
            with _v_col1:
                if f.pe_ratio:
                    _pe_c = "green" if f.pe_ratio < 15 else "orange" if f.pe_ratio < 25 else "red"
                    st.markdown(f"<span title='Price-to-Earnings: stock price divided by earnings per share. Lower = cheaper. Under 15 is attractive, over 25 is expensive.'>"
                                f"<b>P/E Ratio</b></span><br><span style='color:{_pe_c};font-size:1.4em'>"
                                f"{f.pe_ratio:.1f}</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span title='Price-to-Earnings ratio not available (company may not be profitable)'><b>P/E Ratio</b></span><br>N/A", unsafe_allow_html=True)
            with _v_col2:
                if f.forward_pe:
                    _fpe_c = "green" if f.forward_pe < 15 else "orange" if f.forward_pe < 25 else "red"
                    st.markdown(f"<span title='Forward P/E uses estimated future earnings instead of trailing. Lower than trailing P/E means analysts expect earnings growth.'>"
                                f"<b>Forward P/E</b></span><br><span style='color:{_fpe_c};font-size:1.4em'>"
                                f"{f.forward_pe:.1f}</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span title='Forward P/E uses estimated future earnings. Not available for this stock.'><b>Forward P/E</b></span><br>N/A", unsafe_allow_html=True)
            with _v_col3:
                if f.peg_ratio:
                    _peg_c = "green" if f.peg_ratio < 1 else "orange" if f.peg_ratio < 2 else "red"
                    st.markdown(f"<span title='PEG = P/E divided by earnings growth rate. Under 1.0 means the stock is cheap relative to its growth. Over 2.0 is expensive.'>"
                                f"<b>PEG Ratio</b></span><br><span style='color:{_peg_c};font-size:1.4em'>"
                                f"{f.peg_ratio:.2f}</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span title='PEG = P/E divided by growth rate. Not available (needs earnings growth data).'><b>PEG Ratio</b></span><br>N/A", unsafe_allow_html=True)
            with _v_col4:
                if f.price_to_book:
                    _pb_c = "green" if f.price_to_book < 3 else "orange" if f.price_to_book < 5 else "red"
                    st.markdown(f"<span title='Price-to-Book: stock price vs net asset value. Under 1.0 means stock trades below its book value (potential bargain). Under 3 is reasonable.'>"
                                f"<b>P/B Ratio</b></span><br><span style='color:{_pb_c};font-size:1.4em'>"
                                f"{f.price_to_book:.2f}</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span title='Price-to-Book value not available.'><b>P/B Ratio</b></span><br>N/A", unsafe_allow_html=True)
            with _v_col5:
                if f.price_to_sales:
                    _ps_c = "green" if f.price_to_sales < 3 else "orange" if f.price_to_sales < 8 else "red"
                    st.markdown(f"<span title='Price-to-Sales: market cap divided by revenue. Useful for unprofitable companies. Under 3 is cheap, over 8 is expensive.'>"
                                f"<b>P/S Ratio</b></span><br><span style='color:{_ps_c};font-size:1.4em'>"
                                f"{f.price_to_sales:.2f}</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span title='Price-to-Sales: market cap divided by revenue. Not available for this stock.'><b>P/S Ratio</b></span><br>N/A", unsafe_allow_html=True)

            st.markdown("---")

            # ── Profitability ──
            st.markdown("##### Profitability & Growth")
            _p_col1, _p_col2, _p_col3, _p_col4, _p_col5 = st.columns(5)
            with _p_col1:
                if f.revenue:
                    _rev = f"${f.revenue/1e9:.1f}B" if f.revenue >= 1e9 else f"${f.revenue/1e6:.0f}M"
                    st.metric("Revenue (TTM)", _rev,
                              help="Total revenue over the trailing twelve months. Shows the company's scale and top-line sales")
            with _p_col2:
                if f.net_income:
                    _ni = f"${f.net_income/1e9:.1f}B" if abs(f.net_income) >= 1e9 else f"${f.net_income/1e6:.0f}M"
                    st.metric("Net Income", _ni,
                              help="Profit after all expenses, taxes, and costs. Negative means the company is losing money")
            with _p_col3:
                if f.revenue_growth is not None:
                    _rg_c = "normal" if f.revenue_growth >= 0 else "inverse"
                    st.metric("Revenue Growth", f"{f.revenue_growth:.1%}",
                              delta=f"{f.revenue_growth:.1%}", delta_color=_rg_c,
                              help="Year-over-year revenue growth rate. Over 20% is strong growth, negative means revenue is shrinking")
            with _p_col4:
                if f.profit_margin is not None:
                    st.metric("Profit Margin", f"{f.profit_margin:.1%}",
                              help="Net income as percentage of revenue. Higher = more profitable. Over 20% is excellent, under 5% is thin")
            with _p_col5:
                if f.operating_margin is not None:
                    st.metric("Operating Margin", f"{f.operating_margin:.1%}",
                              help="Operating profit as percentage of revenue (before interest and taxes). Shows core business profitability")

            # Profitability bar chart
            _prof_data = {}
            if f.profit_margin is not None:
                _prof_data["Profit Margin"] = f.profit_margin * 100
            if f.operating_margin is not None:
                _prof_data["Op Margin"] = f.operating_margin * 100
            if f.return_on_equity is not None:
                _prof_data["ROE"] = f.return_on_equity * 100
            if _prof_data:
                _prof_tooltips = {
                    "Profit Margin": "Net income as % of revenue. Higher = more profitable",
                    "Op Margin": "Operating profit as % of revenue. Core business profitability",
                    "ROE": "Return on Equity: profit generated per dollar of shareholder equity. Over 15% is strong",
                }
                _prof_hover = [_prof_tooltips.get(k, k) for k in _prof_data.keys()]
                _prof_fig = go.Figure(go.Bar(
                    x=list(_prof_data.keys()), y=list(_prof_data.values()),
                    marker_color=["#4CAF50" if v > 0 else "#f44336" for v in _prof_data.values()],
                    text=[f"{v:.1f}%" for v in _prof_data.values()], textposition="outside",
                    customdata=_prof_hover,
                    hovertemplate="%{x}: %{y:.1f}%<br>%{customdata}<extra></extra>",
                ))
                _prof_fig.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0),
                                        yaxis_title="%", showlegend=False)
                st.plotly_chart(_prof_fig, use_container_width=True)

            st.markdown("---")

            # ── Balance Sheet & Financial Health ──
            st.markdown("##### Financial Health")
            _b_col1, _b_col2, _b_col3, _b_col4, _b_col5 = st.columns(5)
            with _b_col1:
                if f.total_cash:
                    _cash = f"${f.total_cash/1e9:.1f}B" if f.total_cash >= 1e9 else f"${f.total_cash/1e6:.0f}M"
                    st.metric("Cash", _cash,
                              help="Total cash and short-term investments. More cash = more flexibility and safety in downturns")
            with _b_col2:
                if f.total_debt:
                    _debt = f"${f.total_debt/1e9:.1f}B" if f.total_debt >= 1e9 else f"${f.total_debt/1e6:.0f}M"
                    st.metric("Total Debt", _debt,
                              help="Total long-term and short-term debt. High debt increases risk, especially when interest rates rise")
            with _b_col3:
                if f.free_cash_flow:
                    _fcf = f"${f.free_cash_flow/1e9:.1f}B" if abs(f.free_cash_flow) >= 1e9 else f"${f.free_cash_flow/1e6:.0f}M"
                    st.metric("Free Cash Flow", _fcf,
                              help="Cash generated after capital expenditures. This is the real money available for dividends, buybacks, and growth. Positive FCF is essential")
            with _b_col4:
                if f.debt_to_equity is not None:
                    _de_c = "green" if f.debt_to_equity < 50 else "orange" if f.debt_to_equity < 100 else "red"
                    st.markdown(f"<span title='Debt-to-Equity: total debt divided by shareholder equity. Under 50% is conservative, over 100% is heavily leveraged and risky.'>"
                                f"<b>Debt/Equity</b></span><br><span style='color:{_de_c};font-size:1.4em'>"
                                f"{f.debt_to_equity:.1f}%</span>", unsafe_allow_html=True)
            with _b_col5:
                if f.current_ratio is not None:
                    _cr_c = "green" if f.current_ratio > 1.5 else "orange" if f.current_ratio > 1.0 else "red"
                    st.markdown(f"<span title='Current Ratio: current assets divided by current liabilities. Over 1.5 is healthy (can pay short-term bills easily). Below 1.0 means potential liquidity problems.'>"
                                f"<b>Current Ratio</b></span><br><span style='color:{_cr_c};font-size:1.4em'>"
                                f"{f.current_ratio:.2f}</span>", unsafe_allow_html=True)

            # Cash vs Debt visual
            if f.total_cash and f.total_debt:
                _cd_fig = go.Figure()
                _cd_fig.add_trace(go.Bar(name="Cash", x=["Balance Sheet"], y=[f.total_cash/1e9],
                                         marker_color="#4CAF50", text=[f"${f.total_cash/1e9:.1f}B"],
                                         textposition="outside",
                                         hovertemplate="Cash: $%{y:.1f}B<br>Total cash and equivalents available<extra></extra>"))
                _cd_fig.add_trace(go.Bar(name="Debt", x=["Balance Sheet"], y=[f.total_debt/1e9],
                                         marker_color="#f44336", text=[f"${f.total_debt/1e9:.1f}B"],
                                         textposition="outside",
                                         hovertemplate="Debt: $%{y:.1f}B<br>Total long-term and short-term debt<extra></extra>"))
                if f.free_cash_flow:
                    _cd_fig.add_trace(go.Bar(name="FCF", x=["Balance Sheet"],
                                             y=[abs(f.free_cash_flow)/1e9],
                                             marker_color="#2196F3",
                                             text=[f"${f.free_cash_flow/1e9:.1f}B"],
                                             textposition="outside",
                                             hovertemplate="FCF: $%{y:.1f}B<br>Cash generated after capital expenditures<extra></extra>"))
                _cd_fig.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0),
                                      yaxis_title="$ Billions", barmode="group")
                st.plotly_chart(_cd_fig, use_container_width=True)

            st.markdown("---")

            # ── Risk & Short Interest ──
            st.markdown("##### Risk & Short Interest")
            _r_col1, _r_col2, _r_col3, _r_col4 = st.columns(4)
            with _r_col1:
                if f.beta is not None:
                    _beta_c = "green" if f.beta < 1.0 else "orange" if f.beta < 1.5 else "red"
                    _beta_label = "Low vol" if f.beta < 0.8 else "Market-like" if f.beta < 1.2 else "High vol"
                    st.markdown(f"<span title='Beta measures volatility relative to the market. Beta=1.0 moves with the market. Below 1.0 is less volatile (safer). Above 1.5 is very volatile.'>"
                                f"<b>Beta</b></span><br><span style='color:{_beta_c};font-size:1.4em'>"
                                f"{f.beta:.2f}</span> — {_beta_label}", unsafe_allow_html=True)
            with _r_col2:
                if f.short_percent_of_float is not None:
                    _si_c = "green" if f.short_percent_of_float < 0.05 else "orange" if f.short_percent_of_float < 0.15 else "red"
                    st.markdown(f"<span title='Short Interest: percentage of shares being shorted (bet against). Under 5% is normal. Over 15% means many traders expect the price to drop — or could trigger a short squeeze.'>"
                                f"<b>Short Interest</b></span><br><span style='color:{_si_c};font-size:1.4em'>"
                                f"{f.short_percent_of_float:.1%}</span>", unsafe_allow_html=True)
            with _r_col3:
                if f.short_ratio:
                    _sr_c = "green" if f.short_ratio < 3 else "orange" if f.short_ratio < 7 else "red"
                    st.markdown(f"<span title='Days to Cover: how many days it would take all short sellers to buy back shares at average volume. Over 7 days means a short squeeze is more likely.'>"
                                f"<b>Short Ratio</b></span><br><span style='color:{_sr_c};font-size:1.4em'>"
                                f"{f.short_ratio:.1f} days</span>", unsafe_allow_html=True)
            with _r_col4:
                if f.shares_outstanding:
                    _so = f"{f.shares_outstanding/1e9:.2f}B" if f.shares_outstanding >= 1e9 else f"{f.shares_outstanding/1e6:.0f}M"
                    st.metric("Shares Outstanding", _so,
                              help="Total number of shares that exist. Used to calculate market cap (price x shares). More shares = more diluted ownership")

            st.markdown("---")

            # ── Ownership & Analyst ──
            st.markdown("##### Ownership & Analyst Consensus")
            _o_col1, _o_col2, _o_col3 = st.columns(3)

            with _o_col1:
                # Ownership pie chart
                _own_data = {}
                _ins_pct = f.held_pct_insiders or 0
                _inst_pct = f.held_pct_institutions or 0
                _other_pct = max(0, 1 - _ins_pct - _inst_pct)
                if _ins_pct > 0 or _inst_pct > 0:
                    _own_hover = [
                        "Company executives and directors. High insider ownership = aligned incentives with shareholders",
                        "Mutual funds, pension funds, hedge funds. High institutional ownership = professional validation",
                        "Retail investors and other holders. Higher public float = more liquid trading",
                    ]
                    _own_fig = go.Figure(go.Pie(
                        labels=["Insiders", "Institutions", "Public/Other"],
                        values=[_ins_pct * 100, _inst_pct * 100, _other_pct * 100],
                        marker_colors=["#FF9800", "#2196F3", "#9E9E9E"],
                        textinfo="label+percent", hole=0.4,
                        customdata=_own_hover,
                        hovertemplate="%{label}: %{value:.1f}%<br>%{customdata}<extra></extra>",
                    ))
                    _own_fig.update_layout(height=250, margin=dict(l=0, r=0, t=30, b=0),
                                           title_text="Ownership", showlegend=False)
                    st.plotly_chart(_own_fig, use_container_width=True)

            with _o_col2:
                # Insider trading activity
                if f.insider_buys_90d or f.insider_sells_90d:
                    st.markdown("<span title='Insider trading: when company executives and directors buy or sell their own stock. Net buying is bullish — they know the company best.'>"
                                "<b>Insider Activity (90d)</b></span>", unsafe_allow_html=True)
                    _it_fig = go.Figure()
                    _it_fig.add_trace(go.Bar(name="Buys", x=["Insider Trades"],
                                             y=[f.insider_buys_90d], marker_color="#4CAF50"))
                    _it_fig.add_trace(go.Bar(name="Sells", x=["Insider Trades"],
                                             y=[f.insider_sells_90d], marker_color="#f44336"))
                    _it_fig.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0),
                                          barmode="group")
                    st.plotly_chart(_it_fig, use_container_width=True)
                    if f.insider_net_shares:
                        _net_c = "green" if f.insider_net_shares > 0 else "red"
                        _net_label = "net buying" if f.insider_net_shares > 0 else "net selling"
                        st.markdown(f"<span title='Net insider share transactions over 90 days. Net buying = insiders are bullish on their own company (strong signal). Net selling may be routine or concerning.' style='color:{_net_c}'>{_net_label}: "
                                    f"{abs(f.insider_net_shares):,.0f} shares</span>",
                                    unsafe_allow_html=True)

            with _o_col3:
                st.markdown("<span title='Wall Street analyst consensus: aggregated buy/hold/sell recommendations from professional analysts covering this stock.'>"
                            "<b>Analyst Consensus</b></span>", unsafe_allow_html=True)
                if f.analyst_recommendation:
                    _rec_map = {"strong_buy": "Strong Buy", "buy": "Buy", "hold": "Hold",
                                "sell": "Sell", "strong_sell": "Strong Sell"}
                    _rec_colors = {"strong_buy": "green", "buy": "green", "hold": "orange",
                                   "sell": "red", "strong_sell": "red"}
                    _rec_label = _rec_map.get(f.analyst_recommendation, f.analyst_recommendation)
                    _rec_c = _rec_colors.get(f.analyst_recommendation, "gray")
                    st.markdown(f"<span style='color:{_rec_c};font-size:1.4em;font-weight:bold'>"
                                f"{_rec_label}</span>", unsafe_allow_html=True)
                if f.num_analyst_opinions:
                    st.write(f"Based on {f.num_analyst_opinions} analysts")
                if f.analyst_target_price and ql.price:
                    _upside = ((f.analyst_target_price - ql.price.current_price)
                               / ql.price.current_price) * 100
                    _up_c = "green" if _upside > 0 else "red"
                    st.metric("Price Target", f"${f.analyst_target_price:.2f}",
                              delta=f"{_upside:+.1f}% upside",
                              help="Average analyst price target. Positive upside means analysts think the stock is undervalued at current price")
                if f.earnings_date:
                    st.markdown(f"<span title='Date of the next quarterly earnings report. Stock prices often move significantly around earnings. Consider position sizing and stop losses before earnings.'>📅 Next Earnings: {f.earnings_date}</span>", unsafe_allow_html=True)
                if f.dividend_yield and f.dividend_yield > 0:
                    st.metric("Dividend Yield", f"{f.dividend_yield:.2%}",
                              help="Annual dividend payment as percentage of stock price. Higher yield = more income. Over 4% is high yield, but very high yields can signal a company in trouble")

        # ── Business Overview ──
        if f.business_description:
            with st.expander("🏢 Business Overview", expanded=False):
                st.write(f.business_description)
                _biz_cols = st.columns(3)
                with _biz_cols[0]:
                    if f.full_time_employees:
                        st.metric("Employees", f"{f.full_time_employees:,}",
                                  help="Total number of full-time employees")
                with _biz_cols[1]:
                    if f.industry:
                        st.markdown(f"**Industry:** {f.industry}")
                with _biz_cols[2]:
                    if f.competitor_tickers:
                        st.markdown(f"**Competitors:** {', '.join(f.competitor_tickers[:5])}")

        # ── Quarterly Earnings History ──
        if f.quarterly_earnings:
            with st.expander(f"📊 Quarterly Earnings ({len(f.quarterly_earnings)} quarters)", expanded=False):
                _beats = sum(1 for q in f.quarterly_earnings if q.get("surprise_pct", 0) > 0)
                _total_q = len(f.quarterly_earnings)
                _beat_pct = _beats / _total_q * 100 if _total_q > 0 else 0
                _beat_color = "green" if _beat_pct >= 75 else "orange" if _beat_pct >= 50 else "red"
                st.markdown(
                    f"**Beat rate:** <span style='color:{_beat_color};font-weight:bold'>"
                    f"{_beats}/{_total_q} quarters ({_beat_pct:.0f}%)</span>",
                    unsafe_allow_html=True,
                )
                for q in f.quarterly_earnings[:6]:
                    _surp = q.get("surprise_pct", 0)
                    _icon = "🟢" if _surp > 0 else "🔴"
                    _bm = "BEAT" if _surp > 0 else "MISS"
                    st.markdown(
                        f"{_icon} **{q.get('quarter', '?')}**: "
                        f"EPS ${q.get('eps_actual', 'N/A')} vs est ${q.get('eps_estimate', 'N/A')} "
                        f"({_bm} by {abs(_surp):.1f}%)"
                    )
                if f.earnings_news:
                    st.markdown("**Recent Earnings News:**")
                    for _en in f.earnings_news[:4]:
                        st.caption(f"- {_en}")

        # ── Analyst Upgrades/Downgrades ──
        if f.analyst_actions:
            with st.expander(f"📋 Analyst Actions ({len(f.analyst_actions)} recent)", expanded=False):
                for _aa in f.analyst_actions[:10]:
                    _aa_lower = _aa.lower()
                    _aa_icon = "🟢" if "upgrade" in _aa_lower or "buy" in _aa_lower else (
                        "🔴" if "downgrade" in _aa_lower or "sell" in _aa_lower else "⚪"
                    )
                    st.markdown(f"{_aa_icon} {_aa}")

        # ── Top Institutional Holders ──
        if f.top_institutional_holders:
            with st.expander("🏦 Top Institutional Holders", expanded=False):
                for _ih in f.top_institutional_holders[:7]:
                    st.markdown(f"- {_ih}")

        # ── Dividend History ──
        if f.dividend_history_summary:
            with st.expander("💰 Dividend History", expanded=False):
                st.write(f.dividend_history_summary)

    # Refresh button
    _ql_refresh_col, _ql_spacer = st.columns([1, 5])
    with _ql_refresh_col:
        if st.button("Refresh Data", key="refresh_ql"):
            del st.session_state[ql_key]
            st.rerun()

    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 2])
    with col1:
        analyze_button = st.button("🔍 Run Analysis", type="primary", use_container_width=True)

    # Past analysis dropdown
    with col2:
        from src.db.analysis_repo import list_analyses, get_analysis
        _past = run_async(list_analyses(symbol=selected_stock, limit=20))
        if _past:
            _hist_options = {"-- Select past analysis --": None}
            for _a in _past:
                _pos = _a.get("position", "?")
                _conf = _a.get("confidence", 0)
                _date = str(_a.get("created_at", ""))[:16]
                _emj = _POSITION_EMOJI.get(_pos, "")
                _lbl = f"{_emj} {_pos} ({_conf}%) - {_date}"
                _hist_options[_lbl] = _a.get("id")

            _selected_hist = st.selectbox(
                "View past analysis:",
                options=list(_hist_options.keys()),
                index=0,
                key=f"history_{selected_stock}",
                help="Load a previously saved analysis for this stock",
            )

            _hist_id = _hist_options[_selected_hist]
            if _hist_id is not None:
                _loaded = run_async(get_analysis(_hist_id))
                if _loaded and _loaded.recommendation:
                    st.session_state[f"result_{selected_stock}"] = _loaded
                    st.session_state[f"_viewing_historical_{selected_stock}"] = True

    # Show banner if viewing historical analysis
    if st.session_state.get(f"_viewing_historical_{selected_stock}"):
        _hist_rec = st.session_state.get(f"result_{selected_stock}")
        if _hist_rec and _hist_rec.recommendation:
            st.info(f"📜 Viewing saved analysis from {_hist_rec.recommendation.created_at.strftime('%Y-%m-%d %H:%M')}")

    # Show previous results if available
    if f"result_{selected_stock}" in st.session_state:
        transcript = st.session_state[f"result_{selected_stock}"]
        rec = transcript.recommendation

        if rec:
            st.markdown("---")

            # Recommendation header
            pos_val = rec.position.value
            emoji = _POSITION_EMOJI.get(pos_val, "⚪")
            label = _POSITION_LABELS.get(pos_val, pos_val)

            st.header(f"{emoji} {label} — {selected_stock}")

            # ============================================================
            # VIX / FEAR METER — Market Context
            # ============================================================
            data_pkg = st.session_state.get(f"data_{selected_stock}")
            if data_pkg:
                _eco = getattr(data_pkg, "economic", None)
                _sent = getattr(data_pkg, "sentiment", None)
                if _eco or _sent:
                    ctx_cols = st.columns(4)
                    with ctx_cols[0]:
                        if _eco and _eco.vix is not None:
                            vix_label = "Low" if _eco.vix < 15 else ("Elevated" if _eco.vix < 25 else "HIGH")
                            st.metric("VIX", f"{_eco.vix:.1f}", delta=vix_label,
                                      delta_color="normal" if _eco.vix < 20 else "inverse",
                                      help="Volatility Index (fear gauge). Under 15 = calm. Over 25 = fearful. High VIX often signals buying opportunities for patient investors")
                    with ctx_cols[1]:
                        if _sent and getattr(_sent, "fear_greed_index", None) is not None:
                            st.metric("Fear & Greed", f"{_sent.fear_greed_index}/100",
                                      delta=_sent.fear_greed_label,
                                      help="CNN Fear & Greed Index (0-100). Under 25 = Extreme Fear (contrarian buy). Over 75 = Extreme Greed (caution). Best entries happen in fear")
                    with ctx_cols[2]:
                        if _eco and _eco.sp500_level is not None:
                            st.metric("S&P 500", f"{_eco.sp500_level:,.0f}",
                                      delta=f"{_eco.sp500_change_1d_pct:+.2f}%" if _eco.sp500_change_1d_pct else None,
                                      help="S&P 500 index — benchmark for the US stock market. Shows whether the overall market is up or down today")
                    with ctx_cols[3]:
                        if _eco and _eco.yield_curve_spread is not None:
                            yc_label = "INVERTED" if _eco.yield_curve_spread < 0 else "Normal"
                            st.metric("Yield Curve", f"{_eco.yield_curve_spread:+.2f}%", delta=yc_label,
                                      delta_color="inverse" if _eco.yield_curve_spread < 0 else "normal",
                                      help="10Y-2Y Treasury spread. Inverted (negative) historically predicts recession. Normal (positive) = healthy economy")

                    # Market interpretation
                    vix_v = _eco.vix if _eco else None
                    fg_v = _sent.fear_greed_index if _sent and hasattr(_sent, "fear_greed_index") else None
                    if vix_v and fg_v:
                        if vix_v > 25 and fg_v < 30:
                            st.info("📉 Market in FEAR — historically good buying opportunity")
                        elif vix_v < 15 and fg_v > 70:
                            st.warning("📈 Market is GREEDY — be cautious with entry sizing")

            # ============================================================
            # ENTRY & EXIT STRATEGY (MOST IMPORTANT)
            # ============================================================
            st.subheader("🎯 Entry & Exit Strategy")

            col_entry, col_exit, col_risk = st.columns(3)

            with col_entry:
                st.markdown("**Entry Strategy**")
                if rec.entry_price_aggressive:
                    st.metric("Aggressive Entry (buy now)", f"${rec.entry_price_aggressive:.2f}",
                              help="Buy at or near current price if you are confident. Higher risk but captures immediate upside if the stock moves quickly")
                elif rec.entry_price:
                    st.metric("Entry Price", f"${rec.entry_price:.2f}",
                              help="Recommended price to buy the stock. Try to buy at or below this price for optimal risk/reward")
                if rec.entry_price_conservative:
                    st.metric("Conservative Entry (wait for dip)", f"${rec.entry_price_conservative:.2f}",
                              help="Wait for the stock to pull back to this price before buying. Lower risk, better price, but you might miss the move if it never dips this low")
                if rec.scaling_plan:
                    st.caption(f"Scaling: {rec.scaling_plan}")

            with col_exit:
                st.markdown("**Exit Strategy**")
                if rec.exit_price_partial:
                    st.metric("Partial Profit (sell 50%)", f"${rec.exit_price_partial:.2f}",
                              help="Take partial profits here by selling half your position. Locks in gains while letting the rest ride for more upside")
                if rec.exit_price_full:
                    st.metric("Full Target", f"${rec.exit_price_full:.2f}",
                              help="The full price target. Sell remaining shares here. This is where the AI agents believe the stock is fairly valued")
                elif rec.exit_price:
                    st.metric("Exit Price", f"${rec.exit_price:.2f}",
                              help="Target price to sell. This is where the stock is expected to reach based on the analysis")

            with col_risk:
                st.markdown("**Risk Management**")
                if rec.stop_loss_tight:
                    st.metric("Stop Loss (tight)", f"${rec.stop_loss_tight:.2f}",
                              help="Tight stop loss for risk-averse investors. Sell if the stock drops to this price to limit losses. Closer to current price = less risk but more chance of being stopped out on normal volatility")
                if rec.stop_loss_wide:
                    st.metric("Stop Loss (wide)", f"${rec.stop_loss_wide:.2f}",
                              help="Wide stop loss gives the trade more room to breathe. Only triggers on a significant decline. Better for volatile stocks or longer time horizons")
                elif rec.stop_loss:
                    st.metric("Stop Loss", f"${rec.stop_loss:.2f}",
                              help="Exit price to limit losses. If the stock drops to this level, sell to protect your capital. Essential risk management")
                if rec.position_size_pct:
                    st.metric("Position Size", f"{rec.position_size_pct:.0f}% of portfolio",
                              help="Recommended percentage of your total portfolio to allocate to this position. Smaller = safer. Never put more than 10-15% in a single stock")

            # Key metrics row
            cols = st.columns(4)
            with cols[0]:
                st.metric("Confidence", f"{rec.confidence}%",
                          help="How confident the AI agents are in this recommendation (0-100%). Over 70% = strong conviction. Under 50% = mixed signals, proceed with caution")
            with cols[1]:
                st.metric(
                    "Risk/Reward",
                    f"{rec.risk_reward_ratio:.1f}:1" if rec.risk_reward_ratio else "N/A",
                    help="Risk/Reward ratio compares potential gain to potential loss. 3:1 means you could gain $3 for every $1 at risk. Over 2:1 is generally attractive, under 1:1 is not worth it",
                )
            with cols[2]:
                if rec.estimated_upside_pct is not None:
                    st.metric("Potential Upside", f"{rec.estimated_upside_pct:+.1f}%",
                              help="Estimated percentage gain from current price to the target price. Higher = more potential profit")
            with cols[3]:
                if rec.estimated_downside_pct is not None:
                    st.metric("Potential Downside", f"{rec.estimated_downside_pct:+.1f}%",
                              help="Estimated percentage loss from current price to the stop-loss level. This is how much you could lose if the trade goes wrong")

            # Moat Assessment
            if rec.moat_assessment:
                _moat_text = rec.moat_assessment
                _moat_upper = _moat_text.upper()
                if "WIDE" in _moat_upper:
                    _moat_icon = "🏰"
                    _moat_color = "green"
                elif "NARROW" in _moat_upper:
                    _moat_icon = "🛡️"
                    _moat_color = "orange"
                else:
                    _moat_icon = "⚠️"
                    _moat_color = "red"
                st.markdown(
                    f"<span title='Competitive moat assessment: WIDE = strong durable advantage, NARROW = some advantage but vulnerable, NONE = commodity business'>"
                    f"{_moat_icon} <b>Competitive Moat:</b> "
                    f"<span style='color:{_moat_color}'>{_moat_text}</span></span>",
                    unsafe_allow_html=True,
                )

            st.markdown("---")

            # Bull vs Bear case
            col_bull, col_bear = st.columns(2)
            with col_bull:
                st.subheader("🐂 Bull Case")
                st.write(rec.bull_case or "Not available")
            with col_bear:
                st.subheader("🐻 Bear Case")
                st.write(rec.bear_case or "Not available")

            # Key factors
            if rec.key_factors:
                st.subheader("Key Factors")
                for factor in rec.key_factors:
                    st.markdown(f"- {factor}")

            st.markdown("---")

            # ============================================================
            # MULTI-TIMEFRAME OUTLOOK
            # ============================================================
            if rec.outlook_6_months or rec.outlook_1_year or rec.outlook_long_term:
                st.header("🔮 Multi-Timeframe Outlook")
                col_6m, col_1y, col_lt = st.columns(3)
                with col_6m:
                    st.subheader("6 Months")
                    st.write(rec.outlook_6_months or "Not available")
                with col_1y:
                    st.subheader("1 Year")
                    st.write(rec.outlook_1_year or "Not available")
                with col_lt:
                    st.subheader("Long-Term (2-5 yrs)")
                    st.write(rec.outlook_long_term or "Not available")
                st.markdown("---")

            # ============================================================
            # WHAT COULD CHANGE
            # ============================================================
            if rec.what_could_change or rec.contradictory_signals:
                st.header("⚠️ What Could Change This Recommendation")

                if rec.what_could_change:
                    st.subheader("Events That Would Flip the Thesis")
                    for item in rec.what_could_change:
                        st.warning(f"↔️ {item}")

                if rec.contradictory_signals:
                    st.subheader("Contradictory Signals")
                    for signal in rec.contradictory_signals:
                        st.info(f"⚡ {signal}")
                st.markdown("---")

            # ============================================================
            # INFLUENTIAL FIGURES
            # ============================================================
            if rec.influential_figures_summary:
                st.header("👤 Influential Figures & Smart Money")
                st.write(rec.influential_figures_summary)
                st.markdown("---")

            # Additional info
            col_info1, col_info2 = st.columns(2)
            with col_info1:
                st.metric("Time Horizon", rec.time_horizon or "N/A",
                          help="Recommended holding period for this investment. Short-term = weeks, Medium = months, Long-term = 1+ years. Match this to your investment goals")
            with col_info2:
                if rec.sector_etf_suggestion:
                    st.info(f"💡 Sector ETF suggestion: **{rec.sector_etf_suggestion}**")

            # Agent agreement
            agreement_pct = rec.agent_agreement_level * 100
            st.markdown(f"<span title='How much the 5 AI agents agree on the recommendation. 100% = unanimous consensus. Under 60% = significant disagreement — the stock has mixed signals.'>Agent Agreement: {agreement_pct:.0f}%</span>", unsafe_allow_html=True)
            st.progress(rec.agent_agreement_level)

            st.markdown("---")

            # ============================================================
            # SECTOR IMPACT ANALYSIS
            # ============================================================
            sector_analysis = transcript.sector_analysis
            if sector_analysis and not sector_analysis.get("error"):
                st.header("🌍 Sector Impact Analysis")

                # Major events
                major_events = sector_analysis.get("major_events", [])
                if major_events:
                    st.subheader("Major World Events")
                    for event in major_events:
                        severity_emoji = {
                            "critical": "🔴",
                            "high": "🟠",
                            "medium": "🟡",
                            "low": "🟢",
                        }.get(event.get("severity", ""), "⚪")
                        trajectory = event.get("trajectory", "")
                        traj_arrow = {"escalating": "↗️", "stable": "➡️", "de_escalating": "↘️"}.get(trajectory, "")
                        st.markdown(
                            f"- {severity_emoji} **{event.get('event', 'Unknown')}** "
                            f"— Severity: {event.get('severity', 'N/A')} {traj_arrow}"
                        )

                # Sector impacts
                sector_impacts = sector_analysis.get("sector_impacts", [])
                if sector_impacts:
                    st.subheader("Sector Impact Matrix")
                    for sector in sector_impacts:
                        direction = sector.get("impact_direction", "neutral")
                        dir_emoji = {"positive": "📈", "negative": "📉", "neutral": "➡️"}.get(direction, "")
                        magnitude = sector.get("impact_magnitude", "")

                        with st.expander(f"{dir_emoji} **{sector.get('sector', 'Unknown')}** — {direction.upper()} ({magnitude})"):
                            col_imm, col_near, col_med = st.columns(3)
                            with col_imm:
                                st.markdown("**Immediate (0-2 wks)**")
                                st.write(sector.get("immediate_outlook", "N/A"))
                            with col_near:
                                st.markdown("**Near-Term (2-8 wks)**")
                                st.write(sector.get("near_term_outlook", "N/A"))
                            with col_med:
                                st.markdown("**Medium-Term (2-6 mo)**")
                                st.write(sector.get("medium_term_outlook", "N/A"))

                            etfs = sector.get("recommended_etfs", [])
                            stocks = sector.get("recommended_stocks", [])
                            avoid = sector.get("avoid", [])
                            if etfs:
                                st.markdown(f"**ETFs:** {', '.join(etfs)}")
                            if stocks:
                                st.markdown(f"**Stocks:** {', '.join(stocks)}")
                            if avoid:
                                st.markdown(f"**Avoid:** {', '.join(avoid)}")

                # Action recommendations by timeframe
                col_act1, col_act2, col_act3 = st.columns(3)
                with col_act1:
                    st.subheader("⚡ Immediate Actions")
                    for action in sector_analysis.get("immediate_actions", []):
                        st.markdown(f"- {action}")
                with col_act2:
                    st.subheader("📅 Near-Term Actions")
                    for action in sector_analysis.get("near_term_actions", []):
                        st.markdown(f"- {action}")
                with col_act3:
                    st.subheader("📆 Medium-Term Actions")
                    for action in sector_analysis.get("medium_term_actions", []):
                        st.markdown(f"- {action}")

                # Top picks
                top_picks = sector_analysis.get("top_picks", [])
                if top_picks:
                    st.subheader("🏆 Top Picks")
                    pick_cols = st.columns(min(len(top_picks), 4))
                    for i, pick in enumerate(top_picks[:4]):
                        with pick_cols[i]:
                            risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(pick.get("risk_level", ""), "⚪")
                            st.metric(
                                pick.get("ticker", "?"),
                                f"+{pick.get('expected_return_pct', 0):.0f}%",
                                help="AI sector analyst top pick. Expected return based on world events and macro analysis. Risk level shown below with the color dot",
                            )
                            st.caption(f"{risk_emoji} {pick.get('timeframe', '')} | {pick.get('rationale', '')[:80]}")

                # Sectors to avoid
                avoid_sectors = sector_analysis.get("sectors_to_avoid", [])
                if avoid_sectors:
                    st.warning(f"⚠️ **Sectors to Avoid:** {', '.join(avoid_sectors)}")

                # Key risks
                key_risks = sector_analysis.get("key_risks", [])
                if key_risks:
                    with st.expander("🛡️ Key Risks to This Thesis"):
                        for risk in key_risks:
                            st.markdown(f"- {risk}")

                st.markdown("---")

            # ============================================================
            # SOCIAL MEDIA SENTIMENT (Reddit + Twitter)
            # ============================================================
            st.header("📱 Social Media & News Sentiment")

            col_reddit, col_twitter = st.columns(2)

            with col_reddit:
                st.subheader("🤖 Reddit Summary")
                sentiment_agent = None
                for analysis in transcript.phase1_analyses:
                    if analysis.agent_name == "Sentiment Specialist":
                        sentiment_agent = analysis
                        break

                if sentiment_agent:
                    reddit_args = [
                        a for a in sentiment_agent.key_arguments
                        if any(kw in a.claim.lower() for kw in ["reddit", "social", "crowd", "wsb", "r/"])
                    ]
                    if reddit_args:
                        for arg in reddit_args:
                            st.markdown(f"**{arg.claim}**")
                            st.caption(arg.evidence)
                    else:
                        for arg in sentiment_agent.key_arguments[:3]:
                            st.markdown(f"**{arg.claim}**")
                            st.caption(arg.evidence)
                else:
                    st.write("No Reddit data available")

            with col_twitter:
                st.subheader("🐦 Twitter/X Summary")
                if sentiment_agent:
                    twitter_args = [
                        a for a in sentiment_agent.key_arguments
                        if any(kw in a.claim.lower() for kw in ["twitter", "x.com", "tweet", "social media"])
                    ]
                    if twitter_args:
                        for arg in twitter_args:
                            st.markdown(f"**{arg.claim}**")
                            st.caption(arg.evidence)
                    else:
                        shown = set()
                        for arg in sentiment_agent.key_arguments:
                            if arg.claim not in shown and len(shown) < 3:
                                if not any(kw in arg.claim.lower() for kw in ["reddit", "wsb", "r/"]):
                                    st.markdown(f"**{arg.claim}**")
                                    st.caption(arg.evidence)
                                    shown.add(arg.claim)
                else:
                    st.write("No Twitter data available")

            # World News Summary (from Macro Economist)
            st.subheader("🌍 World News & Geopolitical Impact")
            macro_agent = None
            for analysis in transcript.phase1_analyses:
                if analysis.agent_name == "Macro Economist":
                    macro_agent = analysis
                    break

            if macro_agent:
                geo_args = [
                    a for a in macro_agent.key_arguments
                    if any(kw in a.claim.lower() for kw in [
                        "geopolit", "war", "conflict", "sanction", "tariff", "trade",
                        "iran", "china", "russia", "military", "oil", "energy",
                        "hormuz", "strait", "political", "trump", "election",
                        "buffett", "goldman", "jpmorgan", "fed", "institutional",
                    ])
                ]
                if geo_args:
                    for arg in geo_args:
                        strength_emoji = {"strong": "🔴", "moderate": "🟡", "weak": "🟢"}.get(arg.strength, "")
                        st.markdown(f"- {strength_emoji} **{arg.claim}**")
                        st.caption(f"  {arg.evidence}")
                else:
                    for arg in macro_agent.key_arguments[:5]:
                        st.markdown(f"- **{arg.claim}**")
                        st.caption(f"  {arg.evidence}")
            else:
                st.write("No macro/geopolitical analysis available")

            st.markdown("---")

            # ============================================================
            # EMPLOYEE SENTIMENT
            # ============================================================
            data_pkg_emp = st.session_state.get(f"data_{selected_stock}")
            if data_pkg_emp and getattr(data_pkg_emp, "employee_sentiment", None):
                emp = data_pkg_emp.employee_sentiment
                st.header("👥 Employee Sentiment")

                _emp_sent_emoji = {"positive": "🟢", "negative": "🔴", "mixed": "🟡"}.get(emp.overall_sentiment, "⚪")
                st.markdown(f"**Overall: {_emp_sent_emoji} {emp.overall_sentiment.upper()}** ({emp.mention_count} mentions)")

                if emp.key_themes:
                    theme_labels = {
                        "layoffs": "🔴 Layoffs/Restructuring",
                        "hiring_growth": "🟢 Hiring & Growth",
                        "poor_management": "🔴 Poor Management",
                        "good_management": "🟢 Good Management",
                        "innovation": "🟢 Innovation/R&D",
                        "stagnation": "🔴 Stagnation/Outdated",
                        "good_culture": "🟢 Good Culture",
                        "bad_culture": "🔴 Toxic Culture",
                        "compensation": "🟡 Compensation Discussions",
                        "product_quality": "🟡 Product Quality",
                    }
                    _theme_cols = st.columns(min(len(emp.key_themes), 4))
                    for idx, theme in enumerate(emp.key_themes[:8]):
                        with _theme_cols[idx % min(len(emp.key_themes), 4)]:
                            st.markdown(f"**{theme_labels.get(theme, theme)}**")

                # Recurring Issues (confirmed across multiple sources)
                if emp.recurring_issues:
                    st.subheader("🔄 Recurring Issues")
                    _ri_theme_labels = {
                        "layoffs": "Layoffs/Restructuring",
                        "hiring_growth": "Hiring & Growth",
                        "poor_management": "Poor Management",
                        "good_management": "Good Management",
                        "innovation": "Innovation/R&D",
                        "stagnation": "Stagnation/Outdated",
                        "good_culture": "Good Culture",
                        "bad_culture": "Toxic Culture",
                        "compensation": "Compensation",
                        "product_quality": "Product Quality",
                    }
                    for _ri_theme, _ri_data in emp.recurring_issues.items():
                        _ri_total = _ri_data.get("total_mentions", 0)
                        _ri_multi = _ri_data.get("multi_source", False)
                        _ri_label = _ri_theme_labels.get(_ri_theme, _ri_theme)
                        _ri_badge = "Reddit + News" if _ri_multi else (
                            "Reddit" if _ri_data.get("reddit_mentions", 0) > 0 else "News"
                        )
                        _ri_icon = "🔴" if _ri_theme in {"layoffs", "poor_management", "bad_culture", "stagnation"} else (
                            "🟢" if _ri_theme in {"hiring_growth", "good_management", "good_culture", "innovation"} else "🟡"
                        )
                        with st.expander(f"{_ri_icon} {_ri_label} — {_ri_total} mentions ({_ri_badge})", expanded=_ri_multi):
                            _ri_c1, _ri_c2 = st.columns(2)
                            with _ri_c1:
                                st.metric("Reddit", _ri_data.get("reddit_mentions", 0))
                            with _ri_c2:
                                st.metric("News", _ri_data.get("news_mentions", 0))
                            if _ri_data.get("examples"):
                                st.markdown("**Evidence:**")
                                for _ri_ex in _ri_data["examples"]:
                                    st.caption(_ri_ex)

                _emp_col1, _emp_col2 = st.columns(2)
                with _emp_col1:
                    if emp.news_items:
                        st.subheader(f"Employee News ({len(emp.news_items)} articles)")
                        for item in emp.news_items[:5]:
                            st.markdown(f"- **{item.title}** ({item.source})")
                            if item.snippet:
                                st.caption(item.snippet[:150])
                with _emp_col2:
                    if emp.reddit_posts:
                        st.subheader(f"Employee Reddit Posts ({len(emp.reddit_posts)} posts)")
                        for post in emp.reddit_posts[:5]:
                            st.markdown(f"- {post}")

                st.markdown("---")

            # Debate transcript (expandable)
            with st.expander("📜 View Full Debate Transcript"):
                for analysis in transcript.phase1_analyses:
                    st.markdown(f"### {analysis.agent_name}")
                    st.markdown(
                        f"**Position:** {analysis.position.value} | "
                        f"**Confidence:** {analysis.confidence}%"
                    )
                    for arg in analysis.key_arguments:
                        st.markdown(f"- **[{arg.strength}]** {arg.claim}")
                        st.markdown(f"  *Evidence: {arg.evidence}*")
                    if analysis.risks_identified:
                        st.markdown(f"**Risks:** {', '.join(analysis.risks_identified)}")
                    st.markdown("---")

                for round_num, responses in enumerate(transcript.phase2_rounds, 1):
                    st.markdown(f"## Debate Round {round_num}")
                    for resp in responses:
                        st.markdown(f"### {resp.agent_name}")
                        st.markdown(
                            f"**Updated Position:** {resp.updated_position.value} | "
                            f"**Confidence:** {resp.updated_confidence}%"
                        )
                        # Show rebuttals
                        if resp.rebuttals:
                            for reb in resp.rebuttals:
                                _concede_icon = "🤝" if reb.concedes else "⚔️"
                                st.markdown(f"- {_concede_icon} **→ {reb.target_agent}** on *\"{reb.target_claim}\"*")
                                st.markdown(f"  {reb.response}")
                        # Show concessions
                        if resp.concessions:
                            st.markdown(f"**Concessions:** {'; '.join(resp.concessions)}")
                        # Show strongest opposing point
                        if resp.strongest_opposing_point:
                            st.markdown(f"**Strongest opposing point:** {resp.strongest_opposing_point}")
                        # If no rebuttals/concessions (parse failed), show raw reasoning
                        if not resp.rebuttals and not resp.concessions and resp.raw_reasoning:
                            st.caption(resp.raw_reasoning[:500])
                        st.markdown("---")

            # Sector analysis raw reasoning (expandable)
            if sector_analysis and sector_analysis.get("raw_reasoning"):
                with st.expander("📊 View Sector Analyst Full Reasoning"):
                    st.write(sector_analysis["raw_reasoning"])

            # Metadata
            st.caption(
                f"Analysis completed in {rec.analysis_duration_seconds:.1f}s | "
                f"Tokens used: {rec.total_tokens_used:,} | "
                f"Generated at: {rec.created_at.strftime('%Y-%m-%d %H:%M')}"
            )

    # Run analysis
    if analyze_button:
        # Clear historical flag when running new analysis
        st.session_state.pop(f"_viewing_historical_{selected_stock}", None)
        if not settings.gemini_api_key and settings.llm_provider == "gemini":
            st.error(
                "⚠️ Gemini API key not configured. "
                "Add GEMINI_API_KEY to your .env file. "
                "Get a free key at https://aistudio.google.com"
            )
        else:
            import time as _time

            from src.agents.debate_engine import DebateEngine, _get_agent_delay
            from src.agents.token_budget import TokenBudget
            from src.data_collectors.aggregator import DataAggregator
            from src.models.analysis import DebateTranscript
            from src.utils.stock_filters import validate_ticker

            try:
                with st.status(f"🔍 Analyzing {selected_stock}...", expanded=True) as status:

                    # ── Validate ticker ──────────────────────────
                    is_valid, reason = run_async(validate_ticker(selected_stock))
                    if not is_valid:
                        st.error(f"Invalid ticker: {reason}")
                        st.stop()

                    # ── Step 1: Data Collection ──────────────────
                    st.write("📡 **Collecting market data** — 11 sources in parallel...")
                    t0 = _time.time()
                    aggregator = DataAggregator()
                    data_package = run_async(aggregator.collect_all(selected_stock))
                    t_data = _time.time() - t0

                    # Show data collection summary
                    data_lines = []
                    if data_package.price:
                        p = data_package.price
                        data_lines.append(
                            f"💲 Price: **${p.current_price:.2f}** "
                            f"({p.price_change_pct:+.2f}%) — "
                            f"52W: ${p.week_52_low:.0f}–${p.week_52_high:.0f}"
                        )
                    if data_package.fundamentals:
                        f = data_package.fundamentals
                        pe_str = f" · P/E {f.pe_ratio:.1f}" if f.pe_ratio else ""
                        data_lines.append(f"🏢 **{f.company_name}** ({f.sector}){pe_str}")
                    if data_package.technical:
                        t = data_package.technical
                        rsi_str = f" · RSI {t.rsi_14:.0f}" if t.rsi_14 else ""
                        data_lines.append(f"📈 Technical indicators ✓{rsi_str}")
                    if data_package.sentiment:
                        sent = data_package.sentiment
                        sent_parts = []
                        news_items = getattr(sent, "news_items", [])
                        world_items = getattr(sent, "world_news_items", [])
                        if news_items:
                            sent_parts.append(f"{len(news_items)} stock news")
                        if world_items:
                            sent_parts.append(f"{len(world_items)} world news")
                        if getattr(sent, "reddit_mention_count", 0):
                            sent_parts.append(f"{sent.reddit_mention_count} Reddit mentions")
                        if getattr(sent, "twitter_mention_count", 0):
                            sent_parts.append(f"{sent.twitter_mention_count} tweets")
                        if getattr(sent, "fear_greed_index", None) is not None:
                            sent_parts.append(f"Fear&Greed: {sent.fear_greed_index} ({sent.fear_greed_label})")
                        if sent_parts:
                            data_lines.append(f"📰 {' · '.join(sent_parts)}")
                    if data_package.economic:
                        e = data_package.economic
                        econ_parts = []
                        if e.vix is not None:
                            econ_parts.append(f"VIX {e.vix:.1f}")
                        if e.sp500_level is not None:
                            econ_parts.append(f"S&P {e.sp500_level:,.0f}")
                        if e.yield_curve_spread is not None:
                            econ_parts.append(
                                f"Yield curve {'⚠️ inverted' if e.yield_curve_spread < 0 else '✓ normal'}"
                            )
                        if econ_parts:
                            data_lines.append(f"🌐 Macro: {' · '.join(econ_parts)}")
                    if data_package.fundamentals:
                        ff = data_package.fundamentals
                        if ff.insider_buys_90d + ff.insider_sells_90d > 0:
                            data_lines.append(
                                f"🔎 SEC insider trades: {ff.insider_buys_90d} buys, "
                                f"{ff.insider_sells_90d} sells (90d)"
                            )
                    if data_package.employee_sentiment:
                        _es = data_package.employee_sentiment
                        _es_emoji = {"positive": "🟢", "negative": "🔴", "mixed": "🟡"}.get(_es.overall_sentiment, "⚪")
                        data_lines.append(
                            f"👥 Employee sentiment: {_es_emoji} {_es.overall_sentiment} "
                            f"({_es.mention_count} mentions, {len(_es.key_themes)} themes)"
                        )
                    for line in data_lines:
                        st.write(f"  {line}")
                    if data_package.collection_errors:
                        st.write(f"  ⚠️ {len(data_package.collection_errors)} source(s) had issues")
                    st.write(f"  ✅ *Data collected in {t_data:.1f}s*")

                    # ── Step 2: Phase 1 — Agent Analysis ─────────
                    status.update(label=f"🧠 Phase 1: 6 agents analyzing {selected_stock}...")
                    agent_names = [
                        "Stock Analyst", "Sentiment Specialist", "Risk Manager",
                        "Macro Economist", "Technical Analyst", "Sector Analyst",
                    ]
                    st.write(f"🧠 **Phase 1** — {len(agent_names)} AI agents analyzing in parallel...")

                    t1 = _time.time()
                    engine = DebateEngine()
                    budget = TokenBudget()

                    async def _phase1_and_sector():
                        delay = _get_agent_delay()
                        if delay == 0:
                            return await asyncio.gather(
                                engine._phase1_analyze(data_package, budget),
                                engine._run_sector_analysis(data_package, budget),
                            )
                        else:
                            p1 = await engine._phase1_analyze(data_package, budget)
                            sec = await engine._run_sector_analysis(data_package, budget)
                            return p1, sec

                    phase1_results, sector_analysis = run_async(_phase1_and_sector())
                    t_phase1 = _time.time() - t1

                    # Show agent results
                    for a in phase1_results:
                        pos_str = a.position if isinstance(a.position, str) else a.position.value
                        a_emoji = {"STRONG_BUY": "🟢", "BUY": "🟢", "WAIT": "🟡", "AVOID": "🔴", "STRONG_AVOID": "🔴"}.get(pos_str, "⚪")
                        st.write(f"  {a_emoji} **{a.agent_name}**: {pos_str} ({a.confidence}%)")
                    if sector_analysis and not sector_analysis.get("error"):
                        st.write("  🌍 **Sector Analyst**: ✓")
                    st.write(f"  ✅ *Phase 1 completed in {t_phase1:.1f}s*")

                    # ── Step 3: Phase 2 — Debate (conditional) ───
                    should_debate = engine._should_debate(phase1_results)
                    phase2_rounds = []

                    if should_debate:
                        status.update(label=f"💬 Phase 2: Agents debating {selected_stock}...")
                        positions = {
                            (a.position if isinstance(a.position, str) else a.position.value)
                            for a in phase1_results
                        }
                        st.write(f"💬 **Phase 2** — Debate needed ({len(positions)} distinct positions)...")

                        t2 = _time.time()
                        round1 = run_async(
                            engine._phase2_debate_round(data_package, phase1_results, budget)
                        )
                        phase2_rounds.append(round1)

                        r1_positions = set()
                        for r in round1:
                            p = r.updated_position
                            r1_positions.add(p if isinstance(p, str) else p.value)
                        st.write(f"  Round 1 → {', '.join(r1_positions)}")

                        if engine._still_disagreeing(round1):
                            st.write("  ↩️ Still disagreeing — Round 2...")
                            round2 = run_async(
                                engine._phase2_debate_round(data_package, phase1_results, budget)
                            )
                            phase2_rounds.append(round2)
                            st.write("  Round 2 complete")

                        t_phase2 = _time.time() - t2
                        st.write(f"  ✅ *Debate completed in {t_phase2:.1f}s*")
                    else:
                        st.write("💬 **Phase 2** — Skipped (agents already in consensus ✓)")

                    # ── Step 4: Phase 3 — Moderator ──────────────
                    status.update(label=f"⚖️ Phase 3: Synthesizing recommendation for {selected_stock}...")
                    st.write("⚖️ **Phase 3** — Moderator synthesizing final recommendation...")

                    t3 = _time.time()
                    recommendation = run_async(
                        engine.moderator.synthesize(selected_stock, phase1_results, phase2_rounds, budget)
                    )
                    debate_total = _time.time() - t0
                    recommendation.analysis_duration_seconds = debate_total
                    recommendation.total_tokens_used = budget.total_tokens
                    t_phase3 = _time.time() - t3

                    # Build transcript
                    transcript = DebateTranscript(
                        symbol=selected_stock,
                        phase1_analyses=phase1_results,
                        phase2_rounds=phase2_rounds,
                        moderator_synthesis=recommendation.bull_case + " | " + recommendation.bear_case,
                        recommendation=recommendation,
                        sector_analysis=sector_analysis,
                    )

                    pos_val = recommendation.position.value
                    final_emoji = _POSITION_EMOJI.get(pos_val, "⚪")
                    final_label = _POSITION_LABELS.get(pos_val, pos_val)
                    st.write(f"  ✅ *Synthesis completed in {t_phase3:.1f}s*")
                    st.write("")
                    st.write(
                        f"### {final_emoji} {final_label} — "
                        f"{recommendation.confidence}% confidence"
                    )
                    st.write(f"*Total: {debate_total:.1f}s · {budget.total_tokens:,} tokens*")

                    status.update(
                        label=f"✅ {final_emoji} {selected_stock}: {final_label} ({recommendation.confidence}%)",
                        state="complete",
                    )

                    st.session_state[f"result_{selected_stock}"] = transcript
                    st.session_state[f"data_{selected_stock}"] = data_package

                    # Save to database
                    from src.db.analysis_repo import save_analysis
                    run_async(save_analysis(transcript))

                    _time.sleep(2)  # Brief pause so user can see the summary
                    st.rerun()

            except Exception as e:
                st.error(f"Analysis failed: {e}")
                import traceback
                st.code(traceback.format_exc())

else:
    st.info("👆 Add stocks to your watchlist and select one to analyze.")
