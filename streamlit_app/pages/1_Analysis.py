import streamlit as st

st.set_page_config(page_title="Analysis History", page_icon="📈", layout="wide")

st.title("📈 Analysis History")
st.markdown("View past analysis results for tracked stocks.")

# Show all saved results
results = {
    k.replace("result_", ""): v
    for k, v in st.session_state.items()
    if k.startswith("result_")
}

if not results:
    st.info("No analyses yet. Go to the main page and analyze a stock.")
else:
    for symbol, transcript in results.items():
        rec = transcript.recommendation
        if rec:
            emoji = {"STRONG_BUY": "🟢", "BUY": "🟢", "HOLD": "🟡", "SELL": "🔴", "STRONG_SELL": "🔴"}
            with st.expander(
                f"{emoji.get(rec.position.value, '⚪')} {symbol} — "
                f"{rec.position.value} ({rec.confidence}% confidence)"
            ):
                cols = st.columns(4)
                with cols[0]:
                    st.metric("Entry", f"${rec.entry_price:.2f}" if rec.entry_price else "N/A")
                with cols[1]:
                    st.metric("Exit", f"${rec.exit_price:.2f}" if rec.exit_price else "N/A")
                with cols[2]:
                    st.metric("Stop Loss", f"${rec.stop_loss:.2f}" if rec.stop_loss else "N/A")
                with cols[3]:
                    st.metric("Time Horizon", rec.time_horizon or "N/A")

                st.markdown(f"**Bull:** {rec.bull_case}")
                st.markdown(f"**Bear:** {rec.bear_case}")
                st.caption(f"Analyzed: {rec.created_at.strftime('%Y-%m-%d %H:%M')}")
