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


# Sidebar
with st.sidebar:
    st.title("📊 Stock Analyzer")
    st.markdown("---")

    st.subheader("Watchlist")
    watchlist = st.session_state.get("watchlist", settings.default_watchlist.copy())

    # Add stock input
    new_stock = st.text_input("Add stock ticker:", placeholder="e.g., TSLA")
    if st.button("Add to Watchlist") and new_stock:
        ticker = new_stock.upper().strip()
        if ticker not in watchlist:
            watchlist.append(ticker)
            st.session_state["watchlist"] = watchlist
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
                st.rerun()

    st.markdown("---")
    st.caption(f"LLM: {settings.llm_provider.upper()}")
    if settings.gemini_api_key:
        st.caption("Gemini API: Connected ✓")
    else:
        st.caption("Gemini API: Not configured ✗")

# Main content
st.title("Stock Investment Opportunity Analyzer")
st.markdown("*AI-powered multi-agent analysis — should you BUY, WAIT, or AVOID?*")

# Stock selection
selected_stock = st.selectbox(
    "Select a stock to analyze:",
    options=watchlist,
    index=0 if watchlist else None,
)

if selected_stock:
    col1, col2 = st.columns([1, 4])
    with col1:
        analyze_button = st.button("🔍 Run Analysis", type="primary", use_container_width=True)

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
            # ENTRY & EXIT STRATEGY (MOST IMPORTANT)
            # ============================================================
            st.subheader("🎯 Entry & Exit Strategy")

            col_entry, col_exit, col_risk = st.columns(3)

            with col_entry:
                st.markdown("**Entry Strategy**")
                if rec.entry_price_aggressive:
                    st.metric("Aggressive Entry (buy now)", f"${rec.entry_price_aggressive:.2f}")
                elif rec.entry_price:
                    st.metric("Entry Price", f"${rec.entry_price:.2f}")
                if rec.entry_price_conservative:
                    st.metric("Conservative Entry (wait for dip)", f"${rec.entry_price_conservative:.2f}")
                if rec.scaling_plan:
                    st.caption(f"Scaling: {rec.scaling_plan}")

            with col_exit:
                st.markdown("**Exit Strategy**")
                if rec.exit_price_partial:
                    st.metric("Partial Profit (sell 50%)", f"${rec.exit_price_partial:.2f}")
                if rec.exit_price_full:
                    st.metric("Full Target", f"${rec.exit_price_full:.2f}")
                elif rec.exit_price:
                    st.metric("Exit Price", f"${rec.exit_price:.2f}")

            with col_risk:
                st.markdown("**Risk Management**")
                if rec.stop_loss_tight:
                    st.metric("Stop Loss (tight)", f"${rec.stop_loss_tight:.2f}")
                if rec.stop_loss_wide:
                    st.metric("Stop Loss (wide)", f"${rec.stop_loss_wide:.2f}")
                elif rec.stop_loss:
                    st.metric("Stop Loss", f"${rec.stop_loss:.2f}")
                if rec.position_size_pct:
                    st.metric("Position Size", f"{rec.position_size_pct:.0f}% of portfolio")

            # Key metrics row
            cols = st.columns(4)
            with cols[0]:
                st.metric("Confidence", f"{rec.confidence}%")
            with cols[1]:
                st.metric(
                    "Risk/Reward",
                    f"{rec.risk_reward_ratio:.1f}:1" if rec.risk_reward_ratio else "N/A",
                )
            with cols[2]:
                if rec.estimated_upside_pct is not None:
                    st.metric("Potential Upside", f"{rec.estimated_upside_pct:+.1f}%")
            with cols[3]:
                if rec.estimated_downside_pct is not None:
                    st.metric("Potential Downside", f"{rec.estimated_downside_pct:+.1f}%")

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
                st.metric("Time Horizon", rec.time_horizon or "N/A")
            with col_info2:
                if rec.sector_etf_suggestion:
                    st.info(f"💡 Sector ETF suggestion: **{rec.sector_etf_suggestion}**")

            # Agent agreement
            agreement_pct = rec.agent_agreement_level * 100
            st.progress(rec.agent_agreement_level, text=f"Agent Agreement: {agreement_pct:.0f}%")

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
                        if resp.concessions:
                            st.markdown(f"**Concessions:** {'; '.join(resp.concessions)}")
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
                    st.write("📡 **Collecting market data** — 10 sources in parallel...")
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
                    _time.sleep(2)  # Brief pause so user can see the summary
                    st.rerun()

            except Exception as e:
                st.error(f"Analysis failed: {e}")
                import traceback
                st.code(traceback.format_exc())

else:
    st.info("👆 Add stocks to your watchlist and select one to analyze.")
