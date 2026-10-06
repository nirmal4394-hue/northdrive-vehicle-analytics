# Northdrive Vehicle Analytics

An end-to-end analytics app for **Northdrive Auto**, a fictional Canadian online used-car retailer
(buy → recondition → sell online → deliver). It covers the full chain from raw data to decisions:
a data model, SQL analysis, an 11-page dashboard, a days-to-sell prediction model, a pricing advisor,
and an AI tool that answers plain-English questions with SQL.

**Live demo:** _coming soon_

> **Synthetic data.** Every row was randomly generated. Northdrive Auto is not a real company, so the
> findings below show the *method*, not real market facts.

---

## Questions the app answers

| Area | Page | Question |
|---|---|---|
| Performance | Overview | How is the business doing? |
| Performance | Pricing | Does price vs market change how fast cars sell? |
| Performance | Why profit changed | Why did profit per car fall? |
| Operations | Acquisition channels | Where should we buy cars? |
| Operations | Inventory aging | Which cars are sitting too long, and what does it cost? |
| Operations | Delivery economics | Which deliveries lose money? |
| Customers | Shopper funnel | Where do shoppers drop off, and which channels bring buyers? |
| Customers | Returns | What drives 10-day returns, and what do they cost? |
| Predict & recommend | Predict days to sell | How long will this specific car take to sell? |
| Predict & recommend | Pricing advisor | What price earns the most for each unsold car? |
| Predict & recommend | Ask the Data | Any question, in plain English |

## Key findings (illustrative, synthetic data)

- **Pricing:** cars listed 9%+ above market took about 3x longer to sell than cars priced at market.
- **Profit decline:** profit per car fell $921. About 90% was *mix* (buying older cars), not pricing.
  The fix belongs to acquisition, not pricing.
- **Acquisition:** trade-ins earned about $2,230 per car vs $872 for auction cars (transport + recon costs).
  Shifting 10% of auction buying to consumer buy-backs is sized at about $125K.
- **Inventory:** profit per car turned negative after 60 days on the lot; the oldest cars were overpriced from day one.
- **Delivery:** deliveries over 2,500 km lost about $659 each; 30% of one hub's cars crossed the country.
- **Funnel:** referral converted about 6x better than paid social, and profit per buyer was similar,
  so conversion is the lever. Marketing spend data would be needed before moving budget.
- **Returns:** about a third of returns were "condition not as expected": an expectation gap that better
  listings could address.

## How it's built

| Layer | This project | Production equivalent |
|---|---|---|
| Source data | 10 synthetic CSV tables (facts and dimensions) | Website, operations, financing, marketing systems |
| Load / transform | `load_to_sqlite.py` | Airflow + dbt |
| Storage | SQLite | Snowflake |
| Business-ready table | `vehicle_unit_economics` (one row per car) | dbt marts + LookML |
| Dashboards | Streamlit + Plotly | Looker |
| Model | scikit-learn | Python models / ML platform |
| AI questions | Claude API with safety checks | Looker conversational AI |

**Stack:** Python, SQL (SQLite), pandas, Streamlit, Plotly, scikit-learn, Anthropic Claude API, Git.

## The prediction model

Predicts days to sell using only information known on listing day (no leakage).
Average error is about **±19 days vs ±29 days** for simply guessing the median (35% better).
Linear regression matched gradient boosting, so the simpler, explainable model was kept.

One finding from building it: 59 cars were listed 30–116% above market because they cost more to buy
and recondition than they were worth. They distorted the first model until the input was capped,
and they show that **no price can rescue a car that was bought badly.**

Limits: trained on sold cars only (survival analysis is the proper next step), synthetic data, and it
predicts rather than proves cause. Price effects should be confirmed with an experiment.

## The pricing advisor

For each unsold car, it tests 51 prices (-10% to +15% of market), predicts days to sell for each,
and recommends the price with the highest expected profit, compared with wholesaling now.

The first version recommended overpricing, because it ignored automatic price drops and the
**measured 52% historical chance** of a car being wholesaled at day 75. Both were added, plus a
guardrail against raising prices on cars already listed over 45 days.

## Ask the Data: AI with safety layers

Claude writes SQL from a plain-English question; the app shows the answer **and the query**.

1. **Prompt:** read-only rules, standard metric definitions, and worked examples
2. **Safety check:** only a single `SELECT` is allowed; `DELETE`, `DROP` and similar are blocked
3. **Read-only database connection:** writes are physically impossible
4. **Row limit and logging:** at most 1,000 rows, and every question is recorded

Accuracy was improved in the order a careful team would try: clearer definitions, then worked
examples, then (if needed) a stronger model.

## How this was built

Built with AI assistance (Anthropic's Claude), mainly for the Python code. The business questions,
the analysis design, the SQL for the returns analysis, the pricing assumptions, and the validation
of every output are mine. Several first outputs were wrong (a model predicting 31,000 days, an
advisor recommending overpricing) and were caught by checking results against the business.

## Run it locally

```bash
pip install -r requirements.txt
python load_to_sqlite.py      # build the database from the CSVs
python train_model.py         # train the days-to-sell model
streamlit run app.py
```

For Ask the Data, add your own key to a `.env` file: `ANTHROPIC_API_KEY=your-key`.

---

**Nirmal Mohan** · Data Analyst · Mississauga, ON · [LinkedIn](https://linkedin.com/in/nirmal-mohan-84a728ba)