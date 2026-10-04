"""Inventory aging: which cars are sitting too long, what it costs, and what to do."""
import pandas as pd
import plotly.express as px
import streamlit as st

f = st.session_state["units_f"]

st.title("⏳ Inventory aging")
st.caption("Unsold cars as of 2026-09-30. The sale-date filter does not apply to unsold cars. "
           "Holding cost assumes $20 per day.")

BINS, LABELS = [-1, 30, 60, 90, 100000], ["0-30 days", "31-60 days", "61-90 days", "90+ days"]

active = f[f["listing_status"] == "Active"].copy()
exited = f[f["listing_status"].isin(["Retail Sold", "Wholesaled"])].copy()

if active.empty:
    st.warning("No unsold cars match these filters.")
    st.stop()

active["age_band"] = pd.cut(active["days_listed"], BINS, labels=LABELS)
active["price_vs_market_now"] = (active["final_list_price"] / active["market_price_at_listing"] - 1) * 100
exited["age_band"] = pd.cut(exited["days_listed"], BINS, labels=LABELS)

# ---------------- KPIs ----------------
over60 = (active["days_listed"] > 60).sum()
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Unsold cars", f"{len(active):,}")
k2.metric("Median days listed", f"{active['days_listed'].median():.0f}")
k3.metric("Listed over 60 days", f"{over60:,} ({over60 / len(active):.0%})")
k4.metric("Cash tied up", f"${active['total_cost_basis'].sum() / 1e6:,.2f}M")
k5.metric("Holding cost so far", f"${active['carrying_cost_est'].sum() / 1e3:,.0f}K")

# ---------------- Charts ----------------
c1, c2 = st.columns(2)
counts = active.groupby("age_band", observed=False).size().reset_index(name="cars")
c1.plotly_chart(px.bar(counts, x="age_band", y="cars", text="cars",
                       title="Unsold cars by days listed",
                       labels={"age_band": "", "cars": "Cars"}), width="stretch")

gp = (exited.groupby("age_band", observed=False)["total_gross_profit"].mean()
      .round(0).reset_index(name="gp_per_car"))
c2.plotly_chart(px.bar(gp, x="age_band", y="gp_per_car", text="gp_per_car",
                       title="Profit per car collapses after 60 days (sold and wholesaled cars)",
                       labels={"age_band": "Days listed before exit", "gp_per_car": "Avg gross profit ($)"}),
                width="stretch")

pvm = (active.groupby("age_band", observed=False)
       .agg(at_listing=("price_vs_market_pct", "median"), today=("price_vs_market_now", "median"))
       .round(1).reset_index()
       .melt(id_vars="age_band", var_name="when", value_name="pct"))
pvm["when"] = pvm["when"].map({"at_listing": "When listed", "today": "Today"})
st.plotly_chart(px.bar(pvm, x="age_band", y="pct", color="when", barmode="group", text="pct",
                       title="The oldest cars were overpriced from day one (median % above market)",
                       labels={"age_band": "Days listed", "pct": "% vs market", "when": ""}),
                width="stretch")

# ---------------- Action list ----------------
st.subheader("Action list: cars listed over 60 days")
st.caption("Rule of thumb for discussion, not a model: more than 3% above market means reprice; "
           "priced near market but still unsold after 90 days means review for wholesale. "
           "The Day 3 pricing advisor will replace this rule.")

aged = active[active["days_listed"] > 60].copy()


def suggest(row):
    if row["price_vs_market_now"] > 3:
        return "Reprice toward market"
    if row["days_listed"] >= 90:
        return "Wholesale review"
    return "Check listing and photos"


aged["suggested_action"] = aged.apply(suggest, axis=1)
table = (aged.sort_values("days_listed", ascending=False)
         [["vehicle_id", "model_year", "make", "model", "body_type", "days_listed", "num_price_changes",
           "final_list_price", "price_vs_market_now", "total_cost_basis", "carrying_cost_est", "suggested_action"]]
         .rename(columns={"vehicle_id": "Vehicle", "model_year": "Year", "make": "Make", "model": "Model",
                          "body_type": "Body", "days_listed": "Days listed", "num_price_changes": "Price drops",
                          "final_list_price": "Current price", "price_vs_market_now": "% vs market now",
                          "total_cost_basis": "Cost basis", "carrying_cost_est": "Holding cost so far",
                          "suggested_action": "Suggested action"}))

a1, a2, a3 = st.columns(3)
for col, action in zip((a1, a2, a3), ["Reprice toward market", "Wholesale review", "Check listing and photos"]):
    col.metric(action, f"{(aged['suggested_action'] == action).sum():,} cars")

st.dataframe(table, hide_index=True, width="stretch",
             column_config={
                 "Current price": st.column_config.NumberColumn(format="$%d"),
                 "Cost basis": st.column_config.NumberColumn(format="$%d"),
                 "Holding cost so far": st.column_config.NumberColumn(format="$%d"),
                 "% vs market now": st.column_config.NumberColumn(format="%.1f%%"),
             })
st.download_button("Download action list (CSV)", table.to_csv(index=False), "aged_inventory_actions.csv", "text/csv")