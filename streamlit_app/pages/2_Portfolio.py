import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

st.set_page_config(page_title="Portfolio", page_icon="💼", layout="wide")

st.title("💼 Portfolio")
st.markdown("Import your stock purchases and track performance.")

# Initialize portfolio service
if "portfolio_service" not in st.session_state:
    from src.services.portfolio_service import PortfolioService

    st.session_state["portfolio_service"] = PortfolioService()

service = st.session_state["portfolio_service"]

# CSV upload
st.subheader("Import from CSV")
st.caption("Expected columns: symbol, action (BUY/SELL), shares, price, date. Optional: fees, notes")

uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
if uploaded_file is not None:
    content = uploaded_file.read().decode("utf-8")
    imported, errors = service.import_csv(content)
    if imported > 0:
        st.success(f"Imported {imported} transactions")
    if errors:
        with st.expander(f"⚠️ {len(errors)} errors"):
            for err in errors:
                st.warning(err)

# Display portfolio
portfolio = service.get_portfolio()

if portfolio.positions:
    st.subheader("Holdings")

    # Summary metrics
    cols = st.columns(3)
    with cols[0]:
        st.metric("Total Invested", f"${portfolio.total_invested:,.2f}")
    with cols[1]:
        if portfolio.total_current_value is not None:
            st.metric("Current Value", f"${portfolio.total_current_value:,.2f}")
    with cols[2]:
        if portfolio.total_pnl is not None:
            st.metric(
                "Total P&L",
                f"${portfolio.total_pnl:,.2f}",
                delta=f"{portfolio.total_pnl_pct:+.1f}%",
            )

    st.markdown("---")

    # Position details
    for symbol, pos in portfolio.positions.items():
        with st.expander(f"**{symbol}** — {pos.total_shares:.2f} shares"):
            cols = st.columns(4)
            with cols[0]:
                st.metric("Shares", f"{pos.total_shares:.2f}")
            with cols[1]:
                st.metric("Avg Cost", f"${pos.avg_cost_basis:.2f}")
            with cols[2]:
                st.metric("Total Invested", f"${pos.total_invested:,.2f}")
            with cols[3]:
                if pos.unrealized_pnl is not None:
                    st.metric(
                        "Unrealized P&L",
                        f"${pos.unrealized_pnl:,.2f}",
                        delta=f"{pos.unrealized_pnl_pct:+.1f}%",
                    )

            # Transaction history
            if pos.transactions:
                st.markdown("**Transaction History:**")
                for txn in pos.transactions:
                    st.markdown(
                        f"- {txn.date}: {txn.action} {txn.shares} @ ${txn.price_per_share:.2f}"
                        f"{f' (fees: ${txn.fees:.2f})' if txn.fees else ''}"
                    )
else:
    st.info("No portfolio data. Upload a CSV to get started.")

# Sample CSV template
with st.expander("📄 CSV Template"):
    st.code(
        "symbol,action,shares,price,date,fees,notes\n"
        "NVDA,BUY,10,120.50,2024-01-15,4.95,Initial position\n"
        "AAPL,BUY,5,175.00,2024-02-01,0,\n"
        "MSFT,BUY,8,410.25,2024-03-10,4.95,Added on dip",
        language="csv",
    )
