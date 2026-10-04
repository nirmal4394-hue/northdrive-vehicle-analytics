"""Delivery economics: which deliveries lose money, and whether inventory sits where buyers are."""
import pandas as pd
import plotly.express as px
import streamlit as st

sold = st.session_state["sold"]

st.title("🚚 Delivery economics")
st.caption("Completed retail sales (returned sales excluded). Delivery net = fee charged to the customer "
           "minus Northdrive's delivery cost.")

d = sold[sold["returned"] == 0].copy()
if d.empty:
    st.warning("No sales match these filters.")
    st.stop()


def money(v, unit=""):
    """Format dollars with the minus sign before the $ (-$278, not $-278)."""
    scale = {"": 1, "M": 1e6}[unit]
    text = f"${abs(v) / scale:,.{2 if unit else 0}f}{unit}"
    return f"-{text}" if v < 0 else text


REGION = {"ON": "Ontario", "QC": "Quebec", "AB": "Prairies", "SK": "Prairies", "MB": "Prairies",
          "BC": "BC", "NS": "Atlantic", "NB": "Atlantic", "NL": "Atlantic", "PE": "Atlantic"}
d["distance_band"] = pd.cut(d["delivery_km"], [0, 300, 1000, 2500, 100000],
                            labels=["Under 300 km", "300-1,000 km", "1,000-2,500 km", "Over 2,500 km"])
d["region"] = d["delivery_province"].map(REGION)

# ---------------- KPIs ----------------
far = (d["delivery_km"] > 2500).mean()
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Avg delivery cost", money(d["delivery_cost"].mean()))
k2.metric("Avg fee charged", money(d["delivery_fee_charged"].mean()))
k3.metric("Net per delivery", money(d["delivery_net"].mean()))
k4.metric("Total delivery net", money(d["delivery_net"].sum(), "M"))
k5.metric("Shipped over 2,500 km", f"{far:.0%}")

# ---------------- Distance and province ----------------
c1, c2 = st.columns(2)
band = (d.groupby("distance_band", observed=False)
        .agg(sales=("vehicle_id", "count"), net=("delivery_net", "mean"), days=("delivery_days", "mean"))
        .round(1).reset_index())
c1.plotly_chart(px.bar(band, x="distance_band", y="net", text_auto=",.0f", hover_data=["sales", "days"],
                       title="Long-distance deliveries lose the most per car",
                       labels={"distance_band": "", "net": "Delivery net per car ($)", "sales": "Sales",
                               "days": "Avg delivery days"}), width="stretch")
prov = (d.groupby("delivery_province")
        .agg(sales=("vehicle_id", "count"), net=("delivery_net", "mean"), km=("delivery_km", "mean"))
        .round(0).reset_index().sort_values("net"))
c2.plotly_chart(px.bar(prov, x="delivery_province", y="net", text_auto=",.0f", hover_data=["sales", "km"],
                       title="Delivery net per car by province",
                       labels={"delivery_province": "", "net": "Delivery net per car ($)", "sales": "Sales",
                               "km": "Avg km"}), width="stretch")

# ---------------- Where each hub's cars go ----------------
mix = (d.groupby(["recon_hub", "region"]).size().reset_index(name="sales"))
mix["share"] = mix["sales"] / mix.groupby("recon_hub")["sales"].transform("sum") * 100
st.plotly_chart(px.bar(mix, x="share", y="recon_hub", color="region", orientation="h", text_auto=".0f",
                       title="Where each hub's cars are delivered (% of that hub's sales)",
                       labels={"share": "% of hub's sales", "recon_hub": "", "region": "Delivered to"}),
                width="stretch")

# ---------------- Costliest lanes ----------------
st.subheader("Costliest delivery lanes (hub to province)")
lanes = (d.groupby(["recon_hub", "delivery_province"])
         .agg(sales=("vehicle_id", "count"), km=("delivery_km", "mean"), net=("delivery_net", "mean"),
              total_net=("delivery_net", "sum"), gp=("total_gross_profit", "mean"))
         .reset_index().sort_values("total_net").head(10))
st.dataframe(lanes.rename(columns={"recon_hub": "From hub", "delivery_province": "To province", "sales": "Sales",
                                   "km": "Avg km", "net": "Net per delivery", "total_net": "Total delivery net",
                                   "gp": "Total profit per car"}),
             hide_index=True, width="stretch",
             column_config={"Avg km": st.column_config.NumberColumn(format="%d"),
                            "Net per delivery": st.column_config.NumberColumn(format="$%d"),
                            "Total delivery net": st.column_config.NumberColumn(format="$%d"),
                            "Total profit per car": st.column_config.NumberColumn(format="$%d")})

st.info("Hypotheses to test, not conclusions: (1) hold more of the cars Ontario buyers want in the GTA hub, "
        "so fewer cars cross the country; (2) review fees for deliveries over 2,500 km, which today cover "
        "roughly half the cost; (3) free local delivery is a deliberate cost, so test whether it actually "
        "lifts conversion enough to pay for itself.")