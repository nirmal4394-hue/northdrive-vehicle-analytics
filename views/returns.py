"""Returns: what drives 10-day returns and what they cost. The analysis is four SQL queries."""
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st
from data import DB_PATH

st.title("↩️ Returns")
st.caption("Sales up to 2026-09-20 only: sales in the last 10 days could still be returned, so including them "
           "would understate the return rate. This page runs SQL directly, so sidebar filters do not apply.")

# ---------------- The four queries (my SQL) ----------------
Q_GRADE = """
SELECT dv.condition_grade,
       COUNT(fs.vehicle_id)                            AS no_of_sales,
       SUM(fs.returned_within_10_days)                 AS no_returned,
       ROUND(AVG(fs.returned_within_10_days) * 100, 1) AS return_rate_pct
FROM fact_sale fs
JOIN dim_vehicle dv ON dv.vehicle_id = fs.vehicle_id
WHERE fs.sale_date <= '2026-09-20'
GROUP BY dv.condition_grade
ORDER BY dv.condition_grade;
"""

Q_KM = """
SELECT CASE
           WHEN dv.odometer_km_at_acquisition < 50000  THEN 'Under 50,000'
           WHEN dv.odometer_km_at_acquisition < 100000 THEN '50,000-100,000'
           WHEN dv.odometer_km_at_acquisition < 150000 THEN '100,000-150,000'
           ELSE '150,000+'
       END                                             AS km_band,
       COUNT(*)                                        AS no_of_sales,
       SUM(fs.returned_within_10_days)                 AS no_returned,
       ROUND(AVG(fs.returned_within_10_days) * 100, 1) AS return_rate_pct
FROM fact_sale fs
JOIN dim_vehicle dv ON dv.vehicle_id = fs.vehicle_id
WHERE fs.sale_date <= '2026-09-20'
GROUP BY km_band
ORDER BY MIN(dv.odometer_km_at_acquisition);
"""

Q_REASON = """
SELECT return_reason,
       COUNT(*)                                            AS no_returned,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS share_of_returns_pct
FROM fact_sale
WHERE returned_within_10_days = 1
  AND sale_date <= '2026-09-20'
GROUP BY return_reason
ORDER BY no_returned DESC;
"""

Q_COST = """
SELECT COUNT(*)                   AS no_of_returns,
       ROUND(SUM(return_cost), 0) AS total_return_cost,
       ROUND(AVG(return_cost), 0) AS avg_cost_per_return
FROM fact_sale
WHERE returned_within_10_days = 1
  AND sale_date <= '2026-09-20';
"""


@st.cache_data
def run_sql(query):
    """Run a SQL query against the database and return the result as a table."""
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql(query, conn)


grade, km, reason, cost = run_sql(Q_GRADE), run_sql(Q_KM), run_sql(Q_REASON), run_sql(Q_COST)

# ---------------- KPIs ----------------
total_sales, total_returns = grade["no_of_sales"].sum(), grade["no_returned"].sum()
k1, k2, k3, k4 = st.columns(4)
k1.metric("Return rate", f"{total_returns / total_sales:.1%}")
k2.metric("Returns", f"{int(cost.loc[0, 'no_of_returns']):,}")
k3.metric("Total return cost", f"${cost.loc[0, 'total_return_cost'] / 1e3:,.0f}K")
k4.metric("Cost per return", f"${cost.loc[0, 'avg_cost_per_return']:,.0f}")

# ---------------- Drivers ----------------
c1, c2 = st.columns(2)
c1.plotly_chart(px.bar(grade, x="condition_grade", y="return_rate_pct", text="return_rate_pct",
                       hover_data=["no_of_sales", "no_returned"],
                       title="Return rate by condition grade (A = best)",
                       labels={"condition_grade": "Condition grade", "return_rate_pct": "Return rate (%)",
                               "no_of_sales": "Sales", "no_returned": "Returns"}), width="stretch")
c2.plotly_chart(px.bar(km, x="km_band", y="return_rate_pct", text="return_rate_pct",
                       hover_data=["no_of_sales", "no_returned"],
                       title="High-kilometre cars come back more than twice as often",
                       labels={"km_band": "Odometer at purchase", "return_rate_pct": "Return rate (%)",
                               "no_of_sales": "Sales", "no_returned": "Returns"}), width="stretch")

st.plotly_chart(px.bar(reason.sort_values("no_returned"), x="share_of_returns_pct", y="return_reason",
                       orientation="h", text="share_of_returns_pct", hover_data=["no_returned"],
                       title="A third of returns are 'condition not as expected': an expectation gap",
                       labels={"share_of_returns_pct": "% of all returns", "return_reason": "",
                               "no_returned": "Returns"}), width="stretch")

small = grade[grade["no_of_sales"] < 300]["condition_grade"].tolist() + \
        km[km["no_of_sales"] < 300]["km_band"].tolist()
if small:
    st.warning(f"Small groups, read with care: {', '.join(small)} (fewer than 300 sales each).")

top = reason.iloc[0]
st.info(f"Reading: '{top['return_reason']}' is {top['share_of_returns_pct']:.0f}% of returns, roughly "
        f"${top['share_of_returns_pct'] / 100 * cost.loc[0, 'total_return_cost'] / 1e3:,.0f}K of return cost. "
        "That points to listing photos and condition notes before mechanical fixes. Test better disclosure "
        "against conversion, so fewer returns do not come at the cost of fewer sales.")

with st.expander("The SQL behind this page"):
    for title, q in [("1. Return rate by condition grade", Q_GRADE), ("2. Return rate by kilometres", Q_KM),
                     ("3. Returns by reason", Q_REASON), ("4. Return cost", Q_COST)]:
        st.markdown(f"**{title}**")
        st.code(q.strip(), language="sql")