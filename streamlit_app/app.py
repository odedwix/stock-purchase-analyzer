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
    .recommendation-sell { color: #ff1744; font-weight: bold; font-size: 1.5em; }
    .recommendation-hold { color: #ff9100; font-weight: bold; font-size: 1.5em; }
    .confidence-high { color: #00c853; }
    .confidence-medium { color: #ff9100; }
    .confidence-low { color: #ff1744; }
    div[data-testid="stSidebar"] {
        background-color: #1a1a2e;
        color: white;
    }
</style>
""", unsafe_allow_html=True)


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
st.title("Stock Purchase Analyzer")
st.markdown("*AI-powered multi-agent stock analysis with debate-based recommendations*")

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
            position_color = {
                "STRONG_BUY": "🟢", "BUY": "🟢",
                "HOLD": "🟡",
                "SELL": "🔴", "STRONG_SELL": "🔴",
            }
            emoji = position_color.get(rec.position.value, "⚪")

            st.header(f"{emoji} {rec.position.value} — {selected_stock}")

            # Key metrics row
            cols = st.columns(5)
            with cols[0]:
                st.metric("Confidence", f"{rec.confidence}%")
            with cols[1]:
                st.metric("Entry Price", f"${rec.entry_price:.2f}" if rec.entry_price else "N/A")
            with cols[2]:
                st.metric("Exit Price", f"${rec.exit_price:.2f}" if rec.exit_price else "N/A")
            with cols[3]:
                st.metric("Stop Loss", f"${rec.stop_loss:.2f}" if rec.stop_loss else "N/A")
            with cols[4]:
                st.metric(
                    "Risk/Reward",
                    f"{rec.risk_reward_ratio:.1f}:1" if rec.risk_reward_ratio else "N/A",
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

            # Additional info
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.metric("Time Horizon", rec.time_horizon or "N/A")
            with col_info2:
                if rec.estimated_upside_pct is not None:
                    st.metric("Potential Upside", f"{rec.estimated_upside_pct:+.1f}%")
            with col_info3:
                if rec.estimated_downside_pct is not None:
                    st.metric("Potential Downside", f"{rec.estimated_downside_pct:+.1f}%")

            if rec.sector_etf_suggestion:
                st.info(f"💡 Sector ETF suggestion: **{rec.sector_etf_suggestion}**")

            # Agent agreement
            agreement_pct = rec.agent_agreement_level * 100
            st.progress(rec.agent_agreement_level, text=f"Agent Agreement: {agreement_pct:.0f}%")

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
            with st.spinner(f"🔍 Analyzing {selected_stock}... This may take 30-60 seconds."):
                try:
                    from src.services.analysis_service import AnalysisService

                    service = AnalysisService()
                    transcript = run_async(service.analyze_stock(selected_stock))
                    st.session_state[f"result_{selected_stock}"] = transcript
                    st.rerun()
                except Exception as e:
                    st.error(f"Analysis failed: {e}")

else:
    st.info("👆 Add stocks to your watchlist and select one to analyze.")
