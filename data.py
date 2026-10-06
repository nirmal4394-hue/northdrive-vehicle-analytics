"""Shared data loading, used by every page."""
import glob
import os
import sqlite3

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

DB_PATH = "data/database/northdrive.db"
RAW_DIR = "data/raw"


def get_setting(name):
    """Read a secret: first from .env (on your laptop), then from Streamlit secrets (when deployed)."""
    load_dotenv()
    value = os.getenv(name)
    if value:
        return value
    try:
        return st.secrets[name]
    except Exception:
        return None


@st.cache_resource
def ensure_database():
    """Build the database from the CSV files if it does not exist yet (for example, on a fresh deployment)."""
    if os.path.exists(DB_PATH):
        return
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        for path in sorted(glob.glob(os.path.join(RAW_DIR, "*.csv"))):
            table = os.path.splitext(os.path.basename(path))[0]
            pd.read_csv(path).to_sql(table, conn, if_exists="replace", index=False)
        for table, col in [("dim_vehicle", "vehicle_id"), ("fact_acquisition", "vehicle_id"),
                           ("fact_reconditioning", "vehicle_id"), ("fact_listing", "vehicle_id"),
                           ("fact_sale", "vehicle_id"), ("fact_sale", "customer_id"),
                           ("fact_web_leads", "vehicle_id"), ("dim_customer", "customer_id"),
                           ("vehicle_unit_economics", "vehicle_id")]:
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_{col} ON {table}({col})")


def to_flag(x):
    """SQLite stores booleans as 1/0; CSVs may hold 'True'/'False'. Normalise to 1/0."""
    return 1 if x in (1, 1.0, True, "True", "1") else 0


@st.cache_data
def load_table(name):
    """Load any table from the database by name."""
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql(f"SELECT * FROM {name}", conn)


@st.cache_data
def load_units():
    """The one-row-per-vehicle table, with dates parsed and helper columns added."""
    df = load_table("vehicle_unit_economics").copy()
    for c in ["acquisition_date", "list_date", "exit_date", "sale_date"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["returned"] = df["returned_within_10_days"].map(to_flag)
    df["price_band"] = pd.cut(
        df["price_vs_market_pct"], [-100, -3, 0, 3, 6, 9, 100],
        labels=["< -3%", "-3 to 0%", "0 to 3%", "3 to 6%", "6 to 9%", "> 9%"])
    return df