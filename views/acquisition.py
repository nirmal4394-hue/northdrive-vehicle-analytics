"""Acquisition channels: which way of buying cars produces the most profit, and why."""
import plotly.express as px
import streamlit as st

f = st.session_state["units_f"]

st.title("🛒 Acquisition channels")
st.caption("Profit per car counts every car that has left inventory: retail sales (a returned sale counts as its "
           "return cost) and wholesale exits. Unsold cars are excluded. The sale-date filter does not apply here.")

exited = f[f["listing_status"].isin(["Retail Sold", "Wholesaled"])].copy()
if exited.empty:
    st.warning("No cars match these filters.")
    st.stop()

exited["wholesaled"] = (exited["listing_status"] == "Wholesaled").astype(int)
retail = exited[exited["listing_status"] == "Retail Sold"]
bought_df = f.assign(paid_pct=f["acquisition_cost"] / f["market_value_at_acquisition"] * 100)

bought = bought_df.groupby("acquisition_channel").agg(
    cars_bought=("vehicle_id", "count"), paid_pct=("paid_pct", "mean"),
    transport=("inbound_transport_cost", "mean"), recon=("total_recon_cost", "mean"))
outcome = exited.groupby("acquisition_channel").agg(
    wholesale_rate=("wholesaled", "mean"), gp_per_car=("total_gross_profit", "mean"),
    total_gp=("total_gross_profit", "sum"))
retail_stats = retail.groupby("acquisition_channel").agg(
    days_to_sell=("days_listed", "median"), return_rate=("returned", "mean"))
score = (bought.join(outcome).join(retail_stats).reset_index()
         .sort_values("gp_per_car", ascending=False))

# ---------------- Headline: profit per car by channel ----------------
overall = exited["total_gross_profit"].mean()
cols = st.columns(len(score))
for col, (_, r) in zip(cols, score.iterrows()):
    col.metric(r["acquisition_channel"], f"${r['gp_per_car']:,.0f} per car",
               f"{r['gp_per_car'] - overall:+,.0f} vs average")

# ---------------- Charts ----------------
c1, c2 = st.columns(2)
c1.plotly_chart(px.bar(score, x="acquisition_channel", y="gp_per_car", text_auto=",.0f",
                       title="Profit per car by acquisition channel",
                       labels={"acquisition_channel": "", "gp_per_car": "Gross profit per car ($)"}),
                width="stretch")
costs = score.melt(id_vars="acquisition_channel", value_vars=["transport", "recon"],
                   var_name="cost", value_name="dollars")
costs["cost"] = costs["cost"].map({"transport": "Transport to hub", "recon": "Reconditioning"})
c2.plotly_chart(px.bar(costs, x="acquisition_channel", y="dollars", color="cost", text_auto=",.0f",
                       title="Auction cars cost the most to get ready for sale",
                       labels={"acquisition_channel": "", "dollars": "Cost per car ($)", "cost": ""}),
                width="stretch")

# ---------------- Scorecard ----------------
st.subheader("Channel scorecard")
table = score.rename(columns={
    "acquisition_channel": "Channel", "cars_bought": "Cars bought", "paid_pct": "Paid (% of market value)",
    "transport": "Transport / car", "recon": "Recon / car", "days_to_sell": "Median days to sell",
    "wholesale_rate": "Wholesaled", "return_rate": "Returned", "gp_per_car": "Profit / car",
    "total_gp": "Total profit"})
table["Wholesaled"] = table["Wholesaled"] * 100
table["Returned"] = table["Returned"] * 100
st.dataframe(table, hide_index=True, width="stretch",
             column_config={
                 "Paid (% of market value)": st.column_config.NumberColumn(format="%.1f%%"),
                 "Transport / car": st.column_config.NumberColumn(format="$%d"),
                 "Recon / car": st.column_config.NumberColumn(format="$%d"),
                 "Wholesaled": st.column_config.NumberColumn(format="%.1f%%"),
                 "Returned": st.column_config.NumberColumn(format="%.1f%%"),
                 "Profit / car": st.column_config.NumberColumn(format="$%d"),
                 "Total profit": st.column_config.NumberColumn(format="$%d"),
             })

# ---------------- Opportunity sizing ----------------
st.subheader("Opportunity sizing: replace some auction buying with consumer buy-backs")
idx = score.set_index("acquisition_channel")
if {"Auction", "Consumer Buy-Back"}.issubset(idx.index):
    share = st.slider("Share of auction purchases replaced by consumer buy-backs", 0, 30, 10, step=5, format="%d%%")
    auction, buyback = idx.loc["Auction"], idx.loc["Consumer Buy-Back"]
    cars_shifted = round(auction["cars_bought"] * share / 100)
    gain_per_car = buyback["gp_per_car"] - auction["gp_per_car"]
    s1, s2, s3 = st.columns(3)
    s1.metric("Cars shifted", f"{cars_shifted:,}")
    s2.metric("Extra profit per car", f"${gain_per_car:,.0f}")
    s3.metric("Estimated extra profit, same period", f"${cars_shifted * gain_per_car:,.0f}")
    st.caption("Assumptions to test before acting: enough sellers exist to supply these cars, the extra buy-back "
               "cars perform like today's, and attracting them costs less than the profit gained (marketing for "
               "buy-backs is not included here).")
else:
    st.info("Select both Auction and Consumer Buy-Back (or clear the channel filter) to see this estimate.")