import asyncio
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

st.set_page_config(page_title="Analysis History", page_icon="📈", layout="wide")


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


_POSITION_EMOJI = {
    "STRONG_BUY": "🟢", "BUY": "🟢", "WAIT": "🟡", "AVOID": "🔴", "STRONG_AVOID": "🔴",
}

st.title("📈 Analysis History")

from src.db.analysis_repo import list_analyses, get_analysis, get_analyses_for_comparison, delete_analysis

# Filters
col_filter1, col_filter2 = st.columns([1, 3])
with col_filter1:
    symbol_filter = st.text_input("Filter by symbol:", placeholder="e.g., NVDA").upper().strip() or None

analyses = run_async(list_analyses(symbol=symbol_filter, limit=100))

if not analyses:
    st.info("No analyses saved yet. Go to the main page and analyze a stock.")
    st.stop()

st.markdown(f"**{len(analyses)} saved analyses**")

# ── Comparison Section ──
st.subheader("Compare Analyses")
compare_options = {
    f"{a['symbol']} — {a['position']} ({a['confidence']}%) — {a['created_at'][:16]}": a["id"]
    for a in analyses
}
selected_labels = st.multiselect(
    "Select 2-4 analyses to compare side-by-side:",
    options=list(compare_options.keys()),
    max_selections=4,
)

if len(selected_labels) >= 2:
    selected_ids = [compare_options[label] for label in selected_labels]
    transcripts = run_async(get_analyses_for_comparison(selected_ids))

    cols = st.columns(len(transcripts))
    for i, t in enumerate(transcripts):
        rec = t.recommendation
        if not rec:
            continue
        with cols[i]:
            pos_val = rec.position.value
            emoji = _POSITION_EMOJI.get(pos_val, "⚪")
            st.markdown(f"### {emoji} {t.symbol}")
            st.markdown(f"**{pos_val}** — {rec.confidence}%")

            if rec.entry_price_aggressive:
                st.metric("Entry (Aggressive)", f"${rec.entry_price_aggressive:.2f}")
            elif rec.entry_price:
                st.metric("Entry", f"${rec.entry_price:.2f}")

            if rec.exit_price_full:
                st.metric("Target", f"${rec.exit_price_full:.2f}")
            elif rec.exit_price:
                st.metric("Target", f"${rec.exit_price:.2f}")

            if rec.risk_reward_ratio:
                st.metric("Risk/Reward", f"{rec.risk_reward_ratio:.1f}:1")

            if rec.estimated_upside_pct is not None:
                st.metric("Upside", f"{rec.estimated_upside_pct:+.1f}%")

            st.progress(rec.agent_agreement_level, text=f"Agreement: {rec.agent_agreement_level * 100:.0f}%")

            with st.expander("Bull Case"):
                st.write(rec.bull_case or "N/A")
            with st.expander("Bear Case"):
                st.write(rec.bear_case or "N/A")

            st.caption(rec.created_at.strftime("%Y-%m-%d %H:%M"))

    # Sector comparison
    sector_transcripts = [t for t in transcripts if t.sector_analysis and not t.sector_analysis.get("error")]
    if sector_transcripts:
        st.markdown("---")
        st.subheader("Sector Comparison")
        for t in sector_transcripts:
            impacts = t.sector_analysis.get("sector_impacts", [])
            if impacts:
                st.markdown(f"**{t.symbol}** ({t.recommendation.created_at.strftime('%m/%d')})")
                sector_text = []
                for s in impacts:
                    direction = s.get("impact_direction", "neutral")
                    dir_emoji = {"positive": "📈", "negative": "📉", "neutral": "➡️"}.get(direction, "")
                    sector_text.append(f"{dir_emoji} {s.get('sector', '?')}")
                st.write(" · ".join(sector_text))

    st.markdown("---")
elif len(selected_labels) == 1:
    st.info("Select at least 2 analyses to compare.")

# ── History List ──
st.markdown("---")
st.subheader("All Analyses")

for a in analyses:
    pos = a["position"]
    emoji = _POSITION_EMOJI.get(pos, "⚪")
    conf = a["confidence"]
    sym = a["symbol"]
    date_str = a["created_at"][:16]

    with st.expander(f"{emoji} **{sym}** — {pos} ({conf}%) — {date_str}"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Entry", f"${a['entry_price']:.2f}" if a["entry_price"] else "N/A")
        with col2:
            st.metric("Exit", f"${a['exit_price']:.2f}" if a["exit_price"] else "N/A")
        with col3:
            st.metric("Agreement", f"{a['agent_agreement'] * 100:.0f}%" if a["agent_agreement"] else "N/A")
        with col4:
            st.metric("Duration", f"{a['duration_seconds']:.1f}s" if a["duration_seconds"] else "N/A")

        st.markdown(f"**Bull:** {a['bull_case']}")
        st.markdown(f"**Bear:** {a['bear_case']}")
        st.caption(f"Tokens: {a['tokens_used']:,}")

        col_view, col_del = st.columns([3, 1])
        with col_view:
            if st.button("View Full Analysis", key=f"view_{a['id']}"):
                full = run_async(get_analysis(a["id"]))
                if full and full.recommendation:
                    st.session_state[f"result_{full.symbol}"] = full
                    st.success(f"Loaded {full.symbol} analysis. Go to the main page to view it.")
        with col_del:
            if st.button("Delete", key=f"del_{a['id']}"):
                run_async(delete_analysis(a["id"]))
                st.rerun()
