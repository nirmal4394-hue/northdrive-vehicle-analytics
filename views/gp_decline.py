"""Why profit per car changed: a profit bridge and a mix-vs-rate breakdown between two years."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sold = st.session_state["sold"]

st.title("📉 Why profit per car changed")
st.caption("Completed retail sales; returned sales are excluded (the return rate held steady near 5.5% each year). "
           "2026 covers January to September.")

d = sold[sold["returned"] == 0].copy()
d["year"] = d["sale_date"].dt.year
years = sorted(d["year"].unique())
if len(years) < 2:
    st.warning("Pick a sale-date range that covers at least two years.")
    st.stop()

c1, c2 = st.columns(2)
y0 = c1.selectbox("Compare from", years, index=0)
y1 = c2.selectbox("Compare to", years, index=len(years) - 1)
if y0 == y1:
    st.warning("Choose two different years.")
    st.stop()

a, b = d[d["year"] == y0], d[d["year"] == y1]
gp0, gp1 = a["total_gross_profit"].mean(), b["total_gross_profit"].mean()

# ---------------- Mix vs rate by vehicle age ----------------
AGE_BINS, AGE_LABELS = [-1, 2, 4, 6, 50], ["0-2 yrs", "3-4 yrs", "5-6 yrs", "7+ yrs"]
d["age_band"] = pd.cut(d["vehicle_age_at_acquisition"], AGE_BINS, labels=AGE_LABELS)
g = (d[d["year"].isin([y0, y1])].groupby(["year", "age_band"], observed=False)
     .agg(cars=("vehicle_id", "count"), gp=("total_gross_profit", "mean")).reset_index())
g["share"] = g["cars"] / g.groupby("year")["cars"].transform("sum")
s0, s1 = g[g["year"] == y0].set_index("age_band"), g[g["year"] == y1].set_index("age_band")
mix_effect = ((s1["share"] - s0["share"]) * s0["gp"].fillna(0)).sum()
rate_effect = (s1["share"] * (s1["gp"] - s0["gp"]).fillna(0)).sum()
change = gp1 - gp0

k1, k2, k3, k4 = st.columns(4)
k1.metric(f"Profit per car, {y0}", f"${gp0:,.0f}")
k2.metric(f"Profit per car, {y1}", f"${gp1:,.0f}", f"{change:+,.0f}")
k3.metric("Explained by mix (older or newer cars)", f"{mix_effect:+,.0f}")
k4.metric("Explained by rate (same cars, different profit)", f"{rate_effect:+,.0f}")

# ---------------- Profit bridge ----------------
st.subheader(f"Profit bridge: {y0} to {y1} (average per car)")
delta = lambda col: b[col].mean() - a[col].mean()
steps = [("Sale price", delta("sale_price")), ("Purchase cost", -delta("acquisition_cost")),
         ("Transport", -delta("inbound_transport_cost")), ("Reconditioning", -delta("total_recon_cost")),
         ("Financing and add-ons", delta("back_end_gross")), ("Delivery", delta("delivery_net"))]
fig = go.Figure(go.Waterfall(
    measure=["absolute"] + ["relative"] * len(steps) + ["total"],
    x=[f"{y0} profit"] + [s[0] for s in steps] + [f"{y1} profit"],
    y=[gp0] + [s[1] for s in steps] + [0],
    text=[f"${gp0:,.0f}"] + [f"{s[1]:+,.0f}" for s in steps] + [f"${gp1:,.0f}"],
    textposition="outside"))
fig.update_layout(yaxis_title="$ per car", showlegend=False, margin=dict(t=30))
st.plotly_chart(fig, width="stretch")
spread = steps[0][1] + steps[1][1]
st.caption(f"Sale price and purchase cost move together because older cars are cheaper both to buy and to sell. "
           f"Read them as a pair: price minus cost changed by {spread:+,.0f} per car, and reconditioning by "
           f"{steps[3][1]:+,.0f}.")

# ---------------- The mix shift ----------------
c3, c4 = st.columns(2)
mix_plot = g.assign(share_pct=g["share"] * 100, year=g["year"].astype(str))
c3.plotly_chart(px.bar(mix_plot, x="age_band", y="share_pct", color="year", barmode="group", text_auto=".0f",
                       title="We are selling older cars (% of sales by vehicle age)",
                       labels={"age_band": "Vehicle age at purchase", "share_pct": "% of sales", "year": ""}),
                width="stretch")
c4.plotly_chart(px.bar(mix_plot, x="age_band", y="gp", color="year", barmode="group", text_auto=",.0f",
                       title="Profit within each age group barely moved",
                       labels={"age_band": "Vehicle age at purchase", "gp": "Profit per car ($)", "year": ""}),
                width="stretch")

share_of_change = mix_effect / change if change else 0
st.info(f"Reading: about {share_of_change:.0%} of the change comes from mix, meaning the cars we bought got older, "
        f"not from each kind of car becoming less profitable. That points to buying decisions (which cars to acquire, "
        f"and at what price) rather than pricing or operations. Next step: set age and mileage guardrails in a buy box, "
        f"and test whether older cars can be bought cheaply enough to earn their keep.")