"""Pricing advisor: for each unsold car, the list price with the highest expected profit, compared with wholesaling now."""
import json

import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

f = st.session_state["units_f"]

st.title("💡 Pricing advisor")
st.caption("Uses the days-to-sell model to test list prices from -10% to +15% of market, and recommends the price "
           "with the highest expected profit per car. Compared against wholesaling the car now.")


@st.cache_resource
def load_model():
    bundle = joblib.load("models/days_to_sell.joblib")
    with open("models/days_to_sell_metrics.json") as fh:
        return bundle, json.load(fh)


try:
    bundle, m = load_model()
except FileNotFoundError:
    st.error("No trained model found. In the terminal, run:  python train_model.py")
    st.stop()
model, features = bundle["model"], bundle["features"]
cap_lo, cap_hi = m["pvm_cap"]

# ---------------- Business assumptions ----------------
realized = f[(f["listing_status"] == "Retail Sold") & (f["returned"] == 0)]
BACK_END = realized["back_end_gross"].mean()      # average financing + add-on income per sale
DELIVERY = realized["delivery_net"].mean()        # average delivery fee minus cost per sale
WHOLESALE_PCT = 0.86                              # wholesale buyers pay about 86% of market value
PRICE_GRID = np.arange(-10, 15.5, 0.5)            # list prices to test, % vs market
AGED_DAY, DROP, DROP_EVERY = 75, 0.03, 21         # aged-car checkpoint; automatic 3% price drop every 21 days
exited = f[f["listing_status"].isin(["Retail Sold", "Wholesaled"])]
reached = exited[exited["days_listed"] >= AGED_DAY]
WHOLESALE_RISK = (reached["listing_status"] == "Wholesaled").mean() if len(reached) else 0.5

c_hold, c_guard = st.columns(2)
hold = c_hold.slider("Holding cost per day ($)", 10, 40, 20,
                     help="Interest on the money tied up in the car, plus depreciation. An assumption: adjust it.")
STALE_DAYS = 45
guard = c_guard.toggle(f"Guardrail: never raise the price of a car listed over {STALE_DAYS} days", value=True,
                       help="The model treats every car as newly listed. A car still unsold after weeks probably has "
                            "something unappealing the data does not capture, so raising its price is risky.")
st.caption(f"Expected profit = sale price after automatic 3% drops every {DROP_EVERY} days - cost basis - "
           f"(predicted days x ${hold}) + ${BACK_END:,.0f} financing and add-ons - ${abs(DELIVERY):,.0f} delivery. "
           f"If a car is predicted to take over {AGED_DAY} days, history says {WHOLESALE_RISK:.0%} of such cars get "
           f"wholesaled at day {AGED_DAY}, so the profit is weighted by that risk. Wholesale now = {WHOLESALE_PCT:.0%} "
           "of market - cost basis. Holding cost already incurred is sunk, so it is left out. Returns are not modelled.")

active = f[f["listing_status"] == "Active"].copy()
if active.empty:
    st.warning("No unsold cars match these filters.")
    st.stop()


def expected_profit(price, days, cost, market):
    """Expected profit from today if listed at `price`, given predicted days to sell."""
    drops = np.minimum(3, days // DROP_EVERY)
    retail = price * (1 - DROP) ** drops - cost + BACK_END + DELIVERY - days * hold
    wholesale_late = WHOLESALE_PCT * market - cost - AGED_DAY * hold
    return np.where(days > AGED_DAY, WHOLESALE_RISK * wholesale_late + (1 - WHOLESALE_RISK) * retail, retail)


def money(v):
    """-$2,564 rather than $-2,564."""
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


def round_price(p):
    """Retail-style price: nearest $100, minus $5 (e.g. 24,995)."""
    return np.round(p / 100) * 100 - 5


# ---------------- Score every unsold car at every price, in one go ----------------
active["list_month"] = 10  # if re-listed now (October)
grid = active.loc[active.index.repeat(len(PRICE_GRID))].reset_index(drop=True)  # fresh row numbers
grid["price_vs_market_pct"] = np.tile(PRICE_GRID, len(active))
grid["price"] = round_price(grid["market_price_at_listing"] * (1 + grid["price_vs_market_pct"] / 100))
grid["pred_days"] = np.expm1(model.predict(grid[features]))
grid["exp_profit"] = expected_profit(grid["price"], grid["pred_days"], grid["total_cost_basis"],
                                     grid["market_price_at_listing"])
grid["profit_per_day"] = grid["exp_profit"] / grid["pred_days"]
blocked = guard & (grid["days_listed"] > STALE_DAYS) & (grid["price"] > grid["final_list_price"])
grid["allowed_profit"] = grid["exp_profit"].where(~blocked, -np.inf)   # guardrail removes these options
best = grid.loc[grid.groupby("vehicle_id")["allowed_profit"].idxmax()].set_index("vehicle_id")

# Today's price, for comparison (capped to the range the model was trained on)
now = active.copy()
now["pvm_now"] = (now["final_list_price"] / now["market_price_at_listing"] - 1) * 100
now["price_vs_market_pct"] = now["pvm_now"].clip(cap_lo, cap_hi)
now["days_now"] = np.expm1(model.predict(now[features]))
now["profit_now"] = expected_profit(now["final_list_price"], now["days_now"], now["total_cost_basis"],
                                    now["market_price_at_listing"])
now["wholesale_profit"] = round_price(now["market_price_at_listing"] * WHOLESALE_PCT) - now["total_cost_basis"]
now = now.set_index("vehicle_id").join(best[["price", "price_vs_market_pct", "pred_days", "exp_profit",
                                             "profit_per_day"]].rename(columns={"price_vs_market_pct": "rec_pvm"}))


keep = now["profit_now"] >= now["exp_profit"]           # today's price beats every tested price
now.loc[keep, ["price", "exp_profit", "pred_days"]] = now.loc[keep, ["final_list_price", "profit_now", "days_now"]].values
now.loc[keep, "rec_pvm"] = now.loc[keep, "pvm_now"]
now["profit_per_day"] = now["exp_profit"] / now["pred_days"]


def decide(r):
    if r["wholesale_profit"] >= r["exp_profit"]:
        return "Wholesale now"
    if r["price"] < r["final_list_price"] * 0.995:
        return "Reduce price"
    if r["price"] > r["final_list_price"] * 1.005:
        return "Raise price"
    return "Keep price"


now["decision"] = now.apply(decide, axis=1)
now["best_option_profit"] = now[["exp_profit", "wholesale_profit"]].max(axis=1)
now["uplift"] = now["best_option_profit"] - now["profit_now"]

# ---------------- Summary ----------------
counts = now["decision"].value_counts()
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Reduce price", f"{counts.get('Reduce price', 0):,} cars")
k2.metric("Raise price", f"{counts.get('Raise price', 0):,} cars")
k3.metric("Keep price", f"{counts.get('Keep price', 0):,} cars")
k4.metric("Wholesale now", f"{counts.get('Wholesale now', 0):,} cars")
k5.metric("Expected gain vs today's prices", f"${now['uplift'].sum() / 1e3:,.0f}K",
          help="Sum over unsold cars of (best option's expected profit - expected profit at today's price)")
under = (now["best_option_profit"] < 0).sum()
st.info(f"{under} of {len(now)} unsold cars lose money under every option, because they cost more than they are worth. "
        "For those, the advisor picks the smallest loss. The fix for that starts at purchase, not at pricing.")

# ---------------- One car in detail ----------------
st.subheader("One car in detail")
order = now.sort_values("days_listed", ascending=False)
labels = {vid: f"{vid} · {int(r['model_year'])} {r['make']} {r['model']} · {int(r['days_listed'])} days listed"
          for vid, r in order.iterrows()}
vid = st.selectbox("Pick an unsold car", list(labels), format_func=labels.get)
car, curve = now.loc[vid], grid[grid["vehicle_id"] == vid]

a1, a2, a3, a4 = st.columns(4)
a1.metric("Market price", f"${car['market_price_at_listing']:,.0f}")
a2.metric("Current price", f"${car['final_list_price']:,.0f}", f"{car['pvm_now']:+.1f}% vs market", delta_color="off")
a3.metric("Cost basis", f"${car['total_cost_basis']:,.0f}")
a4.metric("Days listed so far", f"{int(car['days_listed'])}")

b1, b2, b3, b4 = st.columns(4)
b1.metric("Recommended price", f"${car['price']:,.0f}", f"{car['rec_pvm']:+.1f}% vs market", delta_color="off")
b2.metric("Predicted days to sell", f"{car['pred_days']:.0f}")
b3.metric("Expected profit", money(car["exp_profit"]), f"{money(car['profit_per_day'])} per day", delta_color="off")
b4.metric("Wholesale now", money(car["wholesale_profit"]))

if car["decision"] == "Wholesale now":
    st.warning(f"Recommendation: wholesale now ({money(car['wholesale_profit'])}). That beats the best retail option "
               f"({money(car['exp_profit'])}) once holding costs, price drops and aging risk are counted.")
elif car["decision"] == "Keep price":
    st.success(f"Recommendation: keep the price at ${car['price']:,.0f}. Expected profit {money(car['exp_profit'])}.")
else:
    st.success(f"Recommendation: {car['decision'].lower()} to ${car['price']:,.0f}. Expected profit "
               f"{money(car['exp_profit'])} vs {money(car['profit_now'])} at today's price.")

fig = px.line(curve, x="price_vs_market_pct", y="exp_profit",
              title="Expected profit for this car at each list price",
              labels={"price_vs_market_pct": "List price vs market (%)", "exp_profit": "Expected profit ($)"})
fig.add_vline(x=car["rec_pvm"], line_dash="dash", annotation_text="Recommended")
fig.add_hline(y=car["wholesale_profit"], line_dash="dot", annotation_text="Wholesale now")
st.plotly_chart(fig, width="stretch")

# ---------------- Every unsold car ----------------
st.subheader("Recommendation for every unsold car")
table = (now.reset_index().sort_values("uplift", ascending=False)
         [["vehicle_id", "model_year", "make", "model", "days_listed", "final_list_price", "price", "pred_days",
           "profit_now", "exp_profit", "wholesale_profit", "decision", "uplift"]]
         .rename(columns={"vehicle_id": "Vehicle", "model_year": "Year", "make": "Make", "model": "Model",
                          "days_listed": "Days listed", "final_list_price": "Current price",
                          "price": "Recommended price", "pred_days": "Predicted days",
                          "profit_now": "Profit at current price", "exp_profit": "Profit at recommended",
                          "wholesale_profit": "Profit if wholesaled", "decision": "Decision",
                          "uplift": "Expected gain"}))
dollars = st.column_config.NumberColumn(format="$%d")
st.dataframe(table, hide_index=True, width="stretch",
             column_config={c: dollars for c in ["Current price", "Recommended price", "Profit at current price",
                                               "Profit at recommended", "Profit if wholesaled", "Expected gain"]}
             | {"Predicted days": st.column_config.NumberColumn(format="%d")})
st.download_button("Download recommendations (CSV)", table.to_csv(index=False), "pricing_recommendations.csv",
                   "text/csv")

with st.expander("Limits of this advisor"):
    st.markdown("""
- **Built on the days-to-sell model**, so it inherits its limits: about ±19 days of error, trained on sold cars only.
- **Predicted days are treated as days from now** if the car is re-priced today; the model was trained on days from first listing.
- **Price drops and the risk of wholesale at day 75 are included**, using the automatic drop rule and the historical
  wholesale rate. Returns are not modelled, and financing and delivery use average values.
- **Holding cost and the 86% wholesale value are assumptions.** Adjust the slider to see how sensitive the answer is.
- **It does not prove that a price change causes faster sales.** Before rolling it out, test it: apply the advisor's
  prices to half of comparable cars and compare against the other half.
""")