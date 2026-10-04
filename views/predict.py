"""Model A in action: predict days to sell for any car, and see how price changes the prediction."""
import json

import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.title("🔮 Predict days to sell")
st.caption("A model trained on past retail sales. Enter a car's details at the moment it is listed.")


@st.cache_resource
def load_model():
    bundle = joblib.load("models/days_to_sell.joblib")
    with open("models/days_to_sell_metrics.json") as fh:
        metrics = json.load(fh)
    return bundle, metrics


try:
    bundle, m = load_model()
except FileNotFoundError:
    st.error("No trained model found. In the terminal, run:  python train_model.py")
    st.stop()

model, features = bundle["model"], bundle["features"]
lo, hi = m["pvm_cap"]

# ---------------- How good is it? ----------------
model_mae = m["mae_linear_days"] if m["model"] == "Linear regression" else m["mae_gbm_days"]
improvement = 1 - model_mae / m["mae_baseline_days"]
k1, k2, k3, k4 = st.columns(4)
k1.metric("Model", m["model"])
k2.metric("Average error", f"±{model_mae:.1f} days")
k3.metric("Guessing the median", f"±{m['mae_baseline_days']:.1f} days")
k4.metric("Better than guessing", f"{improvement:.0%}")

# ---------------- Try a car ----------------
st.subheader("Try a car")
opt = m["options"]
c1, c2, c3, c4 = st.columns(4)
body = c1.selectbox("Body type", opt["body_type"], index=opt["body_type"].index("SUV"))
fuel = c2.selectbox("Fuel type", opt["fuel_type"], index=opt["fuel_type"].index("Gas"))
grade = c3.selectbox("Condition grade", opt["condition_grade"], index=1)
hub = c4.selectbox("Recon hub", opt["recon_hub"])
c5, c6, c7, c8 = st.columns(4)
age = c5.number_input("Vehicle age (years)", 0, 15, 4)
km = c6.number_input("Odometer (km)", 0, 300000, 70000, step=5000)
pvm = c7.slider("List price vs market (%)", float(lo), float(hi), 0.0, step=0.5)
month = c8.selectbox("Month listed", list(range(1, 13)), index=4,
                     format_func=lambda x: pd.Timestamp(2026, x, 1).strftime("%B"))

car = pd.DataFrame([{"body_type": body, "fuel_type": fuel, "condition_grade": grade, "recon_hub": hub,
                     "vehicle_age_at_acquisition": age, "odometer_km_at_acquisition": km,
                     "price_vs_market_pct": pvm, "list_month": month}])[features]
pred = float(np.expm1(model.predict(car))[0])

p1, p2 = st.columns(2)
p1.metric("Predicted days to sell", f"{pred:.0f} days")
p2.metric("Estimated holding cost", f"${pred * 20:,.0f}", help="At the $20 per day assumption")

# ---------------- Same car, different prices ----------------
grid = pd.concat([car.assign(price_vs_market_pct=p) for p in np.arange(-10, 20.5, 0.5)], ignore_index=True)
grid["predicted_days"] = np.expm1(model.predict(grid[features]))
fig = px.line(grid, x="price_vs_market_pct", y="predicted_days",
              title="For this car, pricing above market adds days on the lot",
              labels={"price_vs_market_pct": "List price vs market (%)", "predicted_days": "Predicted days to sell"})
fig.add_vline(x=pvm, line_dash="dash")
st.plotly_chart(fig, width="stretch")

# ---------------- What drives the prediction ----------------
imp = pd.DataFrame(m["importance"], columns=["input", "importance"]).sort_values("importance")
st.plotly_chart(px.bar(imp, x="importance", y="input", orientation="h",
                       title="What drives the prediction (how much worse it gets when an input is scrambled)",
                       labels={"importance": "Importance", "input": ""}), width="stretch")

with st.expander("Limits of this model"):
    st.markdown(f"""
- **Trained on sold cars only.** Unsold cars have not finished their story, so slow sellers are under-represented.
  Survival analysis is the proper fix for that.
- **Wholesaled cars are excluded**, because they were removed at day 75 rather than sold.
- **Price vs market is capped at {lo}% to +{hi}%.** {m['underwater_cars']} cars were listed over 30% above market
  because they cost more than they were worth; the model does not try to predict those.
- **Average error is about ±{model_mae:.0f} days**, so treat a prediction as a range, not a promise.
- **The data is synthetic**, so the model largely rediscovers the rules the data was built with.
  On real data, expect lower accuracy.
- **It predicts, it does not prove cause.** Testing price changes in an experiment is how you would confirm the price effect.
""")