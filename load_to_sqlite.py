"""
Load the Northdrive Auto CSVs into one SQLite database.
Run from the project folder (with venv active):   python load_to_sqlite.py
"""
import os
import glob
import sqlite3
import pandas as pd

RAW_DIR = os.path.join("data", "raw")
DB_DIR = os.path.join("data", "database")
DB_PATH = os.path.join(DB_DIR, "northdrive.db")

os.makedirs(DB_DIR, exist_ok=True)
files = sorted(glob.glob(os.path.join(RAW_DIR, "*.csv")))
if not files:
    raise SystemExit(f"No CSV files found in {RAW_DIR}. Check you copied them there.")

conn = sqlite3.connect(DB_PATH)
for path in files:
    table = os.path.splitext(os.path.basename(path))[0]
    df = pd.read_csv(path)
    df.to_sql(table, conn, if_exists="replace", index=False)
    print(f"Loaded {table:26s} {len(df):>8,d} rows")

# Indexes on the join keys make queries much faster
cur = conn.cursor()
for table, col in [("dim_vehicle", "vehicle_id"), ("fact_acquisition", "vehicle_id"),
                   ("fact_reconditioning", "vehicle_id"), ("fact_listing", "vehicle_id"),
                   ("fact_sale", "vehicle_id"), ("fact_sale", "customer_id"),
                   ("fact_web_leads", "vehicle_id"), ("dim_customer", "customer_id"),
                   ("vehicle_unit_economics", "vehicle_id")]:
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_{col} ON {table}({col})")
conn.commit()

# Sanity check: a real join across tables
check = pd.read_sql("""
    SELECT v.body_type,
           COUNT(*)                    AS units_sold,
           ROUND(AVG(s.sale_price), 0) AS avg_sale_price,
           ROUND(AVG(l.days_listed), 1) AS avg_days_listed
    FROM fact_sale s
    JOIN dim_vehicle  v ON v.vehicle_id = s.vehicle_id
    JOIN fact_listing l ON l.vehicle_id = s.vehicle_id
    GROUP BY v.body_type
    ORDER BY units_sold DESC
""", conn)
print("\nSanity check - sales by body type:")
print(check.to_string(index=False))

conn.close()
print(f"\nDone. Database saved to {DB_PATH}")