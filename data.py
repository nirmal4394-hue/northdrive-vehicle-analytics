"""Shared data loading, used by every page."""
import sqlite3
import pandas as pd
import streamlit as st

DB_PATH = "data/database/northdrive.db"


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