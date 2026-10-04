"""Overview: headline KPIs and monthly trends."""
import plotly.express as px
import streamlit as st

f = st.session_state["units_f"]
sold = st.session_state["sold"]

st.title("🚗 Northdrive Auto: Overview")
st.caption("Headline performance for an online used-vehicle retailer.")

if sold.empty:
    st.warning("No sales match these filters.")
    st.stop()

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
                        labels={"month": "", "gp_per_unit": "GP per unit ($)"}), width="stretch")