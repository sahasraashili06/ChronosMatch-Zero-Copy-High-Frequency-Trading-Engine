
import sys
from pathlib import Path

import streamlit as st
import pandas as pd

# Connect existing Python engine
ROOT = Path(__file__).resolve().parent
PYTHON_DIR = ROOT / "python"
sys.path.insert(0, str(PYTHON_DIR))

from chronosx.oms import OrderManagementSystem, OrderRequest
from chronosx.risk_engine import RiskEngine
from chronosx.types import Side, OrderType


st.set_page_config(
    page_title="ChronosMatch Pro",
    page_icon="⚡",
    layout="wide"
)


def initialize():
    st.session_state.oms = OrderManagementSystem(RiskEngine())
    st.session_state.next_id = 1
    st.session_state.trades = []
    st.session_state.order_logs = []
    st.session_state.active_orders = {}


if "oms" not in st.session_state:
    initialize()


def format_price(price):
    return f"${price / 10000:.4f}"


st.title("⚡ ChronosMatch Pro")
st.subheader("Zero-Copy High-Frequency Trading Engine")
st.caption("Python Edition | Interactive Academic Project Demo")

st.success("SIMULATION MODE — No real exchange connection")

with st.sidebar:
    st.header("Control Panel")
    st.write("Engine: ChronosMatch Python")
    st.write("Order Management: Active")
    st.write("Risk Validation: Enabled")

    if st.button("Reset Simulation"):
        initialize()
        st.rerun()

    st.divider()
    st.caption("Academic Project Demonstration")


oms = st.session_state.oms
book = oms.book

best_bid = book.best_bid()
best_ask = book.best_ask()
spread = book.spread()

c1, c2, c3, c4 = st.columns(4)

c1.metric("Total Orders", oms.order_count)
c2.metric("Active Orders", book.active_order_count())

c3.metric(
    "Best Bid",
    format_price(best_bid) if best_bid is not None else "N/A"
)

c4.metric(
    "Best Ask",
    format_price(best_ask) if best_ask is not None else "N/A"
)

if spread is not None:
    st.metric("Current Spread", format_price(spread))

st.divider()

# ORDER PLACEMENT
st.header("Trading Operations")

with st.form("order_form"):

    col1, col2, col3 = st.columns(3)

    with col1:
        side = st.selectbox("Order Side", ["BUY", "SELL"])

    with col2:
        order_type = st.selectbox(
            "Order Type", ["Limit", "Market"]
        )

    with col3:
        quantity = st.number_input(
            "Quantity",
            min_value=1,
            max_value=100000,
            value=10,
            step=1
        )

    if order_type == "Limit":
        price = st.number_input(
            "Limit Price ($)",
            min_value=0.0001,
            value=10.0000,
            step=0.0001,
            format="%.4f"
        )
    else:
        price = 0.0
        st.info("Market order uses available opposite-side liquidity.")

    submitted = st.form_submit_button(
        "Submit Order",
        type="primary",
        use_container_width=True
    )

    if submitted:

        order_id = st.session_state.next_id

        request = OrderRequest(
            id=order_id,
            side=Side.Buy if side == "BUY" else Side.Sell,
            type=(
                OrderType.Limit
                if order_type == "Limit"
                else OrderType.Market
            ),
            price=int(round(price * 10000)),
            qty=int(quantity)
        )

        response = oms.submit(request)
        result = response.match_result
        status = result.final_status.name

        st.session_state.next_id += 1

        risk = response.risk_result.name

        st.session_state.order_logs.append({
            "Order ID": order_id,
            "Side": side,
            "Type": order_type,
            "Price": (
                format_price(int(round(price * 10000)))
                if order_type == "Limit"
                else "Market"
            ),
            "Quantity": int(quantity),
            "Status": status,
            "Risk": risk
        })

        if status in ("New", "PartiallyFilled"):
            st.session_state.active_orders[order_id] = (
                f"{side} | {order_type} | Order #{order_id}"
            )
        else:
            st.session_state.active_orders.pop(order_id, None)

        for trade in result.trades:
            st.session_state.trades.append({
                "Aggressor ID": trade.aggressor_id,
                "Resting ID": trade.resting_id,
                "Execution Price": format_price(trade.price),
                "Quantity": trade.qty
            })

        if risk != "Approved":
            st.error(f"Risk validation: {risk}")
        else:
            st.success(
                f"Order #{order_id} processed. Status: {status}"
            )

        if result.cancel_event:
            st.warning(
                f"Residual quantity cancelled: "
                f"{result.cancel_event.remaining_qty}"
            )

        st.rerun()


st.divider()

# ORDER BOOK
st.header("Live Order Book")

bid_col, ask_col = st.columns(2)

try:
    bids = book.top_bids(depth=10)
    asks = book.top_asks(depth=10)

    with bid_col:
        st.subheader("🟢 BUY / BIDS")

        bid_data = [
            {"Price": format_price(p), "Quantity": q}
            for p, q in bids
        ]

        st.dataframe(
            pd.DataFrame(bid_data, columns=["Price", "Quantity"]),
            use_container_width=True,
            hide_index=True
        )

    with ask_col:
        st.subheader("🔴 SELL / ASKS")

        ask_data = [
            {"Price": format_price(p), "Quantity": q}
            for p, q in asks
        ]

        st.dataframe(
            pd.DataFrame(ask_data, columns=["Price", "Quantity"]),
            use_container_width=True,
            hide_index=True
        )

except Exception as error:
    st.warning(f"Order book display: {error}")


st.divider()

# TRADE HISTORY
st.header("Executed Trade History")

if st.session_state.trades:

    st.dataframe(
        pd.DataFrame(st.session_state.trades),
        use_container_width=True,
        hide_index=True
    )

else:
    st.info("No matched trades yet. Submit opposite-side matching orders.")


# ORDER HISTORY
st.header("Order History")

if st.session_state.order_logs:

    st.dataframe(
        pd.DataFrame(st.session_state.order_logs),
        use_container_width=True,
        hide_index=True
    )

else:
    st.info("No orders submitted yet.")


# ORDER CANCELLATION
st.divider()
st.header("Order Cancellation")

active = st.session_state.active_orders

if active:

    selected_id = st.selectbox(
        "Select an active order",
        options=list(active.keys()),
        format_func=lambda x: active[x]
    )

    if st.button("Cancel Selected Order"):

        cancel_response = oms.cancel(selected_id)
        cancel_result = cancel_response.match_result

        st.session_state.active_orders.pop(selected_id, None)

        st.session_state.order_logs.append({
            "Order ID": selected_id,
            "Side": "CANCEL",
            "Type": "-",
            "Price": "-",
            "Quantity": "-",
            "Status": cancel_result.final_status.name,
            "Risk": "-"
        })

        if cancel_result.cancel_event:
            st.success(
                f"Order cancelled. Remaining quantity: "
                f"{cancel_result.cancel_event.remaining_qty}"
            )
        else:
            st.info(
                f"Cancellation result: "
                f"{cancel_result.final_status.name}"
            )

        st.rerun()

else:
    st.info("No active orders available for cancellation.")


st.divider()

# PROJECT VERIFICATION
st.header("Project Verification")

v1, v2 = st.columns(2)

v1.metric("Previously Passed Tests", "374 / 374")
v2.metric("Previously Measured Coverage", "85%")

st.caption(
    "ChronosMatch Pro | Python HFT Matching Engine | "
    "Academic Simulation"
)
