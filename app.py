"""
Northdrive Auto - Vehicle Analytics
Entry point: loads data, draws the shared filters, then runs the selected page.
Run:  streamlit run app.py
"""
import pandas as pd
import streamlit as st
from data import load_units

st.set_page_config(page_title="Northdrive Auto | Vehicle Analytics", page_icon="🚗", layout="wide")

units = load_units()

# ---------------- Shared filters (apply to every page) ----------------
st.sidebar.header("Filters")
min_d, max_d = units["sale_date"].min().date(), units["sale_date"].max().date()
date_range = st.sidebar.date_input("Sale date range", (min_d, max_d), min_value=min_d, max_value=max_d)
bodies = st.sidebar.multiselect("Body type", sorted(units["body_type"].unique()))
hubs = st.sidebar.multiselect("Recon hub", sorted(units["recon_hub"].unique()))
channels = st.sidebar.multiselect("Acquisition channel", sorted(units["acquisition_channel"].unique()))
st.sidebar.caption("Synthetic data: Northdrive Auto is a fictional company.")

f = units.copy()
if bodies:
    f = f[f["body_type"].isin(bodies)]
if hubs:
    f = f[f["recon_hub"].isin(hubs)]
if channels:
    f = f[f["acquisition_channel"].isin(channels)]

sold = f[f["listing_status"] == "Retail Sold"]
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    sold = sold[(sold["sale_date"] >= start) & (sold["sale_date"] <= end)]

# Pages read these instead of re-filtering
st.session_state["units_f"] = f
st.session_state["sold"] = sold

# ---------------- Navigation ----------------
pg = st.navigation({
    "Performance": [
        st.Page("views/overview.py", title="Overview", icon="📊", default=True),
        st.Page("views/pricing.py", title="Pricing", icon="🏷️"),
        st.Page("views/gp_decline.py", title="Why profit changed", icon="📉"),
    ],
    "Operations": [
        st.Page("views/acquisition.py", title="Acquisition channels", icon="🛒"),
        st.Page("views/inventory.py", title="Inventory aging", icon="⏳"),
        st.Page("views/delivery.py", title="Delivery economics", icon="🚚"),
    ],
       "Customers": [
        st.Page("views/funnel.py", title="Shopper funnel", icon="🧭"),
        st.Page("views/returns.py", title="Returns", icon="↩️"),
    ],
            "Predict and recommend": [
        st.Page("views/predict.py", title="Predict days to sell", icon="🔮"),
        st.Page("views/advisor.py", title="Pricing advisor", icon="💡"),
        st.Page("views/ask.py", title="Ask the Data", icon="💬"),
    ],
})
pg.run()