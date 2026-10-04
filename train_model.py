"""
Model A: predict days to sell for a vehicle at the moment it is listed.
Run from the project folder (venv active):   python train_model.py
Saves models/days_to_sell.joblib and models/days_to_sell_metrics.json
"""
import json
import os
import sqlite3

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

DB_PATH = "data/database/northdrive.db"
os.makedirs("models", exist_ok=True)

# 1. Data: retail-sold cars only. Active cars have not finished selling (see notes),
#    and wholesaled cars were removed at day 75, so their "days" is not a true sale time.
with sqlite3.connect(DB_PATH) as conn:
    df = pd.read_sql("SELECT * FROM vehicle_unit_economics WHERE listing_status = 'Retail Sold'", conn)
df["list_month"] = pd.to_datetime(df["list_date"]).dt.month

# A few cars cost more to buy and recondition than they were worth, so they were listed 30-116% above
# market and sat for months. Cap this input at -15% / +25% so extreme values cannot distort the model.
PVM_CAP = (-15, 25)
underwater = int((df["price_vs_market_pct"] > 30).sum())
df["price_vs_market_pct"] = df["price_vs_market_pct"].clip(*PVM_CAP)

# 2. Features = only what we know ON THE DAY THE CAR IS LISTED.
#    No sale price, price drops or exit date: those are only known after the sale (that would be "leakage").
CATEGORICAL = ["body_type", "fuel_type", "condition_grade", "recon_hub"]
NUMERIC = ["vehicle_age_at_acquisition", "odometer_km_at_acquisition", "price_vs_market_pct", "list_month"]
FEATURES = CATEGORICAL + NUMERIC
X, y = df[FEATURES], df["days_listed"]

# 3. Hold back 20% of cars the model never sees during training, to test it honestly.
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

prep = ColumnTransformer([
    ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL),
    ("num", "passthrough", NUMERIC)])

# Days to sell is skewed (a few cars take very long), so models learn log(days) and convert back.
def fit_and_score(model):
    pipe = Pipeline([("prep", prep), ("model", model)])
    pipe.fit(X_train, np.log1p(y_train))
    pred = np.expm1(pipe.predict(X_test))
    return pipe, mean_absolute_error(y_test, pred)

# 4. Compare against a simple baseline: guess the median for every car.
mae_baseline = mean_absolute_error(y_test, np.full(len(y_test), y_train.median()))
linear, mae_linear = fit_and_score(LinearRegression())
gbm, mae_gbm = fit_and_score(HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=42))
best, best_name = (gbm, "Gradient boosting") if mae_gbm <= mae_linear else (linear, "Linear regression")

# 5. Which inputs matter most? Shuffle one input at a time and see how much worse predictions get.
imp = permutation_importance(best, X_test, np.log1p(y_test), n_repeats=5, random_state=42)
importance = sorted(zip(FEATURES, imp.importances_mean.round(4).tolist()), key=lambda t: -t[1])

joblib.dump({"model": best, "features": FEATURES, "categorical": CATEGORICAL, "numeric": NUMERIC}, "models/days_to_sell.joblib")
metrics = {"model": best_name, "pvm_cap": PVM_CAP, "underwater_cars": underwater, "n_train": len(X_train), "n_test": len(X_test),
           "mae_baseline_days": round(mae_baseline, 1), "mae_linear_days": round(mae_linear, 1),
           "mae_gbm_days": round(mae_gbm, 1), "median_days": float(y.median()),
           "importance": importance,
           "options": {c: sorted(df[c].dropna().unique().tolist()) for c in CATEGORICAL}}
with open("models/days_to_sell_metrics.json", "w") as fh:
    json.dump(metrics, fh, indent=2)

print(f"Capped price vs market at {PVM_CAP}; {underwater} cars were listed over 30% above market")
print(f"Trained on {len(X_train):,} cars, tested on {len(X_test):,} unseen cars")
print(f"Average error, guessing the median: {mae_baseline:.1f} days")
print(f"Average error, linear regression:   {mae_linear:.1f} days")
print(f"Average error, gradient boosting:   {mae_gbm:.1f} days")
print(f"Saved: {best_name}")
print("Most important inputs:", ", ".join(f"{k} ({v:.3f})" for k, v in importance[:4]))