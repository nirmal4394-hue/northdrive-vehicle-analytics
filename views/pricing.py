"""Pricing: how list price vs market affects speed of sale and profit."""
import plotly.express as px
import streamlit as st

sold = st.session_state["sold"]

st.title("🏷️ Pricing")
st.caption("How far above or below market we list a car, and what that does to speed and profit.")

if sold.empty:
    st.warning("No sales match these filters.")
    st.stop()

band = (sold.groupby("price_band", observed=True)
        .agg(units=("vehicle_id", "count"),
             median_days=("days_listed", "median"),
             gp_per_unit=("total_gross_profit", "mean"))
        .reset_index())

st.subheader("Cars priced well above market sit much longer")
st.plotly_chart(px.bar(band, x="price_band", y="median_days", text="median_days",
                       labels={"price_band": "List price vs market", "median_days": "Median days to sell"}),
                width="stretch")
st.dataframe(band.rename(columns={"price_band": "Price vs market", "units": "Units",
                                  "median_days": "Median days to sell", "gp_per_unit": "GP per unit ($)"}),
             hide_index=True, width="stretch")