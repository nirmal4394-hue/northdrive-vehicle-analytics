"""
Northdrive Auto - Vehicle Analytics (Day 1 skeleton)
Run from the project folder (venv active):   streamlit run app.py
"""
import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st

DB_PATH = "data/database/northdrive.db"

st.set_page_config(page_title="Northdrive Auto | Vehicle Analytics", page_icon="🚗", layout="wide")


def to_flag(x):
    """SQLite stores booleans as 1/0; CSVs may hold 'True'/'False'. Normalise to 1/0."""
    return 1 if x in (1, 1.0, True, "True", "1") else 0


@st.cache_data
def load_units():
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql("SELECT * FROM vehicle_unit_economics", conn)
    for c in ["acquisition_date", "list_date", "exit_date", "sale_date"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["returned"] = df["returned_within_10_days"].map(to_flag)
    df["price_band"] = pd.cut(
        df["price_vs_market_pct"], [-100, -3, 0, 3, 6, 9, 100],
        labels=["< -3%", "-3 to 0%", "0 to 3%", "3 to 6%", "6 to 9%", "> 9%"])
    return df


units = load_units()

# ---------------- Sidebar filters ----------------
st.sidebar.header("Filters")
min_d, max_d = units["sale_date"].min().date(), units["sale_date"].max().date()
date_range = st.sidebar.date_input("Sale date range", (min_d, max_d), min_value=min_d, max_value=max_d)
bodies = st.sidebar.multiselect("Body type", sorted(units["body_type"].unique()))
hubs = st.sidebar.multiselect("Recon hub", sorted(units["recon_hub"].unique()))
channels = st.sidebar.multiselect("Acquisition channel", sorted(units["acquisition_channel"].unique()))

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

# ---------------- Header ----------------
st.title("🚗 Northdrive Auto: Vehicle Analytics")
st.caption("Pricing, inventory and profitability for an online used-vehicle retailer. "
           "Synthetic data: Northdrive Auto is a fictional company.")

tab_overview, tab_pricing, tab_ai = st.tabs(["Overview", "Pricing", "Ask the Data (coming soon)"])

# ---------------- Overview ----------------
with tab_overview:
    if sold.empty:
        st.warning("No sales match these filters.")
    else:
        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("Units retailed", f"{len(sold):,}")
        k2.metric("Total gross profit", f"${sold['total_gross_profit'].sum() / 1e6:,.2f}M")
        k3.metric("Gross profit / unit", f"${sold['total_gross_profit'].mean():,.0f}")
        k4.metric("Median days to sell", f"{sold['days_listed'].median():.0f}")
        k5.metric("10-day return rate", f"{sold['returned'].mean():.1%}")
        k6.metric("Active inventory", f"{(f['listing_status'] == 'Active').sum():,}")

        monthly = (sold.assign(month=sold["sale_date"].dt.to_period("M").dt.to_timestamp())
                   .groupby("month")
                   .agg(units=("vehicle_id", "count"), gp_per_unit=("total_gross_profit", "mean"))
                   .reset_index())
        c1, c2 = st.columns(2)
        c1.plotly_chart(px.bar(monthly, x="month", y="units", title="Units retailed per month",
                               labels={"month": "", "units": "Units"}), width="stretch")
        c2.plotly_chart(px.line(monthly, x="month", y="gp_per_unit", markers=True,
                                title="Gross profit per unit by month",
                                labels={"month": "", "gp_per_unit": "GP per unit ($)"}),
                        width="stretch")

# ---------------- Pricing ----------------
with tab_pricing:
    if sold.empty:
        st.warning("No sales match these filters.")
    else:
        band = (sold.groupby("price_band", observed=True)
                .agg(units=("vehicle_id", "count"),
                     median_days=("days_listed", "median"),
                     gp_per_unit=("total_gross_profit", "mean"))
                .reset_index())
        st.subheader("How list price vs market affects speed of sale")
        st.plotly_chart(px.bar(band, x="price_band", y="median_days", text="median_days",
                               labels={"price_band": "List price vs market", "median_days": "Median days to sell"}),
                        width="stretch")
        st.dataframe(band.rename(columns={"price_band": "Price vs market", "units": "Units",
                                          "median_days": "Median days to sell", "gp_per_unit": "GP per unit ($)"}),
                     hide_index=True, width="stretch")

# ---------------- AI placeholder ----------------
with tab_ai:
    st.info("Coming on Day 3: ask questions in plain English and get answers from the data, powered by Claude.")