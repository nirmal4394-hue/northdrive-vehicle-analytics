"""Funnel: where shoppers drop off, and which marketing channels bring buyers."""
import plotly.express as px
import streamlit as st
from data import load_table

f = st.session_state["units_f"]

st.title("🧭 Shopper funnel")
st.caption("One row per shopper visit to a vehicle page. Body type, hub and acquisition-channel filters apply "
           "through the vehicle viewed; the sale-date filter does not apply to visits.")

leads = load_table("fact_web_leads")
leads = leads[leads["vehicle_id"].isin(f["vehicle_id"])]
if leads.empty:
    st.warning("No visits match these filters.")
    st.stop()

visits, checkout = len(leads), leads["started_checkout"].sum()
deposit, buyers = leads["deposit_paid"].sum(), leads["purchased"].sum()

# ---------------- KPIs ----------------
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Vehicle page visits", f"{visits:,}")
k2.metric("Started checkout", f"{checkout / visits:.1%}", help="Share of visits")
k3.metric("Paid a deposit", f"{deposit / checkout:.1%}", help="Share of checkouts started")
k4.metric("Purchased", f"{buyers / deposit:.1%}", help="Share of deposits paid")
k5.metric("Visit to purchase", f"{buyers / visits:.2%}")

# ---------------- Funnel + visits vs buyers ----------------
c1, c2 = st.columns(2)
stages = {"Visited a vehicle page": visits, "Started checkout": checkout, "Paid a deposit": deposit,
          "Purchased": buyers}
c1.plotly_chart(px.funnel(x=list(stages.values()), y=list(stages.keys()),
                          title="Nine in ten visitors never start checkout"), width="stretch")

ch = leads.groupby("marketing_channel").agg(visits=("lead_id", "count"), checkout=("started_checkout", "sum"),
                                            deposit=("deposit_paid", "sum"), buyers=("purchased", "sum"))
share = ch[["visits", "buyers"]].div(ch[["visits", "buyers"]].sum()).mul(100).round(1)
share = share.reset_index().melt(id_vars="marketing_channel", var_name="measure", value_name="pct")
share["measure"] = share["measure"].map({"visits": "Share of visits", "buyers": "Share of buyers"})
c2.plotly_chart(px.bar(share, x="pct", y="marketing_channel", color="measure", barmode="group", orientation="h",
                       text_auto=".0f", title="Some channels bring visits, others bring buyers (%)",
                       labels={"pct": "%", "marketing_channel": "", "measure": ""}), width="stretch")

# ---------------- Channel scorecard ----------------
st.subheader("Marketing channel scorecard")
buyer_rows = leads[leads["purchased"] == 1].merge(
    f[["vehicle_id", "total_gross_profit"]], on="vehicle_id", how="left")
ch["visit_to_checkout"] = ch["checkout"] / ch["visits"] * 100
ch["checkout_to_deposit"] = ch["deposit"] / ch["checkout"] * 100
ch["deposit_to_purchase"] = ch["buyers"] / ch["deposit"] * 100
ch["purchase_rate"] = ch["buyers"] / ch["visits"] * 100
ch["gp_per_buyer"] = buyer_rows.groupby("marketing_channel")["total_gross_profit"].mean()
ch["gp_per_1000_visits"] = ch["purchase_rate"] / 100 * ch["gp_per_buyer"] * 1000
card = (ch.reset_index().sort_values("purchase_rate", ascending=False)
        [["marketing_channel", "visits", "visit_to_checkout", "checkout_to_deposit", "deposit_to_purchase",
          "purchase_rate", "gp_per_buyer", "gp_per_1000_visits"]]
        .rename(columns={"marketing_channel": "Channel", "visits": "Visits",
                         "visit_to_checkout": "Visit to checkout", "checkout_to_deposit": "Checkout to deposit",
                         "deposit_to_purchase": "Deposit to purchase", "purchase_rate": "Visit to purchase",
                         "gp_per_buyer": "Profit per buyer", "gp_per_1000_visits": "Profit per 1,000 visits"}))
pct = st.column_config.NumberColumn(format="%.1f%%")
st.dataframe(card, hide_index=True, width="stretch",
             column_config={"Visit to checkout": pct, "Checkout to deposit": pct, "Deposit to purchase": pct,
                            "Visit to purchase": st.column_config.NumberColumn(format="%.2f%%"),
                            "Profit per buyer": st.column_config.NumberColumn(format="$%d"),
                            "Profit per 1,000 visits": st.column_config.NumberColumn(format="$%d")})

# ---------------- Device ----------------
dev = (leads.groupby("device_type").agg(visits=("lead_id", "count"), buyers=("purchased", "sum")).reset_index())
dev["purchase_rate"] = (dev["buyers"] / dev["visits"] * 100).round(2)
dev["share_of_visits"] = (dev["visits"] / dev["visits"].sum() * 100).round(0)
st.plotly_chart(px.bar(dev, x="device_type", y="purchase_rate", text_auto=".2f", hover_data=["share_of_visits"],
                       title="Mobile converts worst, yet most visits are on mobile",
                       labels={"device_type": "", "purchase_rate": "Visit to purchase (%)",
                               "share_of_visits": "% of visits"}), width="stretch")

st.info("What this page cannot answer yet: marketing spend by channel is not in the data, so cost per buyer and "
        "return on spend are unknown. A channel with low conversion can still be worth it if it is cheap. "
        "That spend data is the first thing I would add before moving any budget.")