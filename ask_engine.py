"""
Ask the Data engine: turns a plain-English question into a safe, read-only SQL query using Claude,
runs it, and summarises the answer. Kept separate from the page so it can be tested on its own.
"""
import csv
import json
import os
import re
import sqlite3
from datetime import datetime

import pandas as pd

DB_PATH = "data/database/northdrive.db"
TABLE = "vehicle_unit_economics"
MODEL = "claude-haiku-4-5-20251001"   # cheap and good at SQL; swap for a larger model if accuracy is low
MAX_ROWS = 1000
LOG_PATH = "logs/ask_log.csv"

# Words that change data or the database. Any of these and the query is blocked.
FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|"
                       r"reindex|truncate)\b", re.IGNORECASE)

# Plain-English notes the AI reads alongside each column name (the "semantic layer" in miniature).
COLUMN_NOTES = {
    "vehicle_id": "unique car id",
    "condition_grade": "A (best) to D (worst), assessed when bought",
    "acquisition_channel": "'Auction', 'Consumer Buy-Back', 'Trade-In' or 'Dealer Wholesale'",
    "recon_hub": "'GTA Hub', 'Calgary Hub' or 'Montreal Hub'",
    "listing_status": "'Retail Sold' (sold to a customer), 'Wholesaled' (sold off at a loss) or 'Active' (unsold)",
    "days_listed": "days the car was listed on the website",
    "price_vs_market_pct": "initial list price vs market price, in percent",
    "sale_date": "TEXT 'YYYY-MM-DD'; NULL if not sold",
    "acquisition_date": "TEXT 'YYYY-MM-DD'",
    "list_date": "TEXT 'YYYY-MM-DD'",
    "financed": "1 = customer took a loan, 0 = cash; NULL if not sold",
    "returned_within_10_days": "1 = returned under the 10-day guarantee, 0 = kept; NULL if not sold",
    "total_gross_profit": "profit per car in dollars (front-end + financing/add-ons + delivery); NULL if unsold",
    "total_cost_basis": "acquisition cost + transport + reconditioning",
    "delivery_province": "two-letter province code, e.g. 'ON', 'AB'",
}

SYSTEM_PROMPT = """You are a SQL assistant for Northdrive Auto, an online used-car retailer.
Write ONE SQLite query against the table vehicle_unit_economics (one row per vehicle) to answer the question.

Rules:
- Read-only: a single SELECT (or WITH ... SELECT). Never modify data.
- Use only the columns listed below. Dates are TEXT 'YYYY-MM-DD'.
- Round money to 0 decimals and percentages to 1 decimal.

Standard definitions (use these instead of asking):
- "Sold", "sales", "sold the most/least" = number of retail sales: COUNT(*) WHERE listing_status = 'Retail Sold'.
- "Revenue" = SUM(sale_price) of retail sales.
- "Profit" = total_gross_profit. "Average profit per car" = AVG(total_gross_profit) of retail sales.
- "Car model" = make and model together (GROUP BY make, model).
- "Unsold" or "in stock" = listing_status = 'Active'.
- When a ranking is asked for, show the top 5 rows so near-ties are visible.

When to ask a clarifying question (a last resort):
- Only when the question cannot be answered without guessing a key choice the definitions above do not cover,
  for example "best" or "worst" with no measure. Otherwise answer, and state any assumption in "explanation".
- Never ask what "sold" means: it always means the number of cars sold.

When to refuse:
- If the user asks to change or delete data, or asks about something not in this table.

Reply with JSON only, no other text, in one of these shapes:
{"type": "sql", "sql": "...", "explanation": "one sentence on what the query does and any assumption made"}
{"type": "clarify", "message": "your clarifying question"}
{"type": "refuse", "message": "short reason"}

Columns:
"""


# Worked examples shown to the model before each question. Small models copy examples more reliably than rules.
# Deliberately NOT the questions in the accuracy test, so the test stays fair.
EXAMPLES = [
    ("Which car model sold the most?",
     {"type": "sql",
      "sql": "SELECT make, model, COUNT(*) AS cars_sold FROM vehicle_unit_economics "
             "WHERE listing_status = 'Retail Sold' GROUP BY make, model ORDER BY cars_sold DESC LIMIT 5",
      "explanation": "Counts retail sales per make and model; 'sold' means number of cars sold."}),
    ("Which body type generated the most revenue in 2025?",
     {"type": "sql",
      "sql": "SELECT body_type, ROUND(SUM(sale_price), 0) AS revenue FROM vehicle_unit_economics "
             "WHERE listing_status = 'Retail Sold' AND sale_date BETWEEN '2025-01-01' AND '2025-12-31' "
             "GROUP BY body_type ORDER BY revenue DESC LIMIT 5",
      "explanation": "Revenue = total sale price of 2025 retail sales, by body type."}),
    ("What are our best cars?",
     {"type": "clarify", "message": "Best by which measure: profit per car, number sold, or speed of sale?"}),
    ("Delete all the wholesaled cars",
     {"type": "refuse", "message": "I can only read data, not change or delete it."}),
]


def example_messages():
    """Turn the worked examples into a short pretend conversation the model sees first."""
    msgs = []
    for q, a in EXAMPLES:
        msgs += [{"role": "user", "content": f"Question: {q}"}, {"role": "assistant", "content": json.dumps(a)}]
    return msgs


def schema_text():
    """List every column of the table with its type and plain-English note."""
    with sqlite3.connect(DB_PATH) as conn:
        cols = conn.execute(f"PRAGMA table_info({TABLE})").fetchall()
    lines = []
    for _, name, ctype, *_ in cols:
        note = COLUMN_NOTES.get(name, "")
        lines.append(f"- {name} ({ctype or 'TEXT'})" + (f": {note}" if note else ""))
    return "\n".join(lines)


class AIFormatError(Exception):
    """Claude replied, but not with the JSON we asked for."""


def _parse_json(text):
    """Find the JSON object anywhere in the reply, even if Claude added words or ```json fences around it."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise AIFormatError(text)
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        raise AIFormatError(text)


def generate_sql(client, question, previous_sql=None, error=None):
    """Ask Claude for a query. On a retry, show it the failed query and the error message.
    If the reply is not valid JSON, ask once more with a firm reminder."""
    content = f"Question: {question}"
    if error:
        content += f"\n\nYour previous query failed.\nQuery: {previous_sql}\nError: {error}\nPlease fix it."
    for attempt in range(2):
        if attempt == 1:
            content += "\n\nReply with the JSON object only. No other words before or after it."
        reply = client.messages.create(model=MODEL, max_tokens=800, system=SYSTEM_PROMPT + schema_text(),
                                       messages=example_messages() + [{"role": "user", "content": content}])
        text = reply.content[0].text if reply.content else ""
        try:
            return _parse_json(text)
        except AIFormatError:
            if attempt == 1:
                raise


def validate_sql(sql):
    """Allow exactly one read-only SELECT. Raise ValueError otherwise."""
    cleaned = sql.strip().rstrip(";").strip()
    if ";" in cleaned:
        raise ValueError("Only one statement is allowed.")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")
    if FORBIDDEN.search(cleaned):
        raise ValueError("The query contains a command that could change data.")
    return cleaned


def run_sql(sql):
    """Run a validated query on a READ-ONLY connection, capped at MAX_ROWS rows."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        return pd.read_sql(f"SELECT * FROM ({sql}) LIMIT {MAX_ROWS}", conn)
    finally:
        conn.close()


def summarise(client, question, df):
    """One or two plain sentences answering the question from the result rows only."""
    if df.empty:
        return "The query returned no rows."
    reply = client.messages.create(
        model=MODEL, max_tokens=300,
        system="Answer the question in one or two plain sentences using only the data provided. "
               "Do not invent numbers. Format money with $ and thousands separators.",
        messages=[{"role": "user", "content": f"Question: {question}\n\nResult:\n{df.head(30).to_csv(index=False)}"}])
    return reply.content[0].text.strip()


def log(question, outcome, sql="", rows=0):
    """Keep a record of every question: useful for checking accuracy and spotting misuse."""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    new = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["timestamp", "question", "outcome", "sql", "rows"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), question, outcome, sql, rows])


def ask(client, question):
    """Full pipeline: question -> SQL -> safety check -> run (one retry on error) -> summary."""
    try:
        plan = generate_sql(client, question)
    except AIFormatError as exc:
        log(question, "format_error")
        return {"type": "error", "message": "The AI replied in an unexpected format. Try rephrasing the question. "
                                            f"Its reply started with: {str(exc)[:200]!r}"}
    if plan.get("type") != "sql":
        log(question, plan.get("type", "unknown"))
        return {"type": plan.get("type", "error"), "message": plan.get("message", "No answer.")}

    sql, error = plan["sql"], None
    for attempt in range(2):
        try:
            sql = validate_sql(sql)
            df = run_sql(sql)
            log(question, "answered", sql, len(df))
            return {"type": "answer", "sql": sql, "explanation": plan.get("explanation", ""),
                    "data": df, "summary": summarise(client, question, df), "retried": attempt == 1}
        except ValueError as exc:            # blocked by the safety check: never retry
            log(question, "blocked", sql)
            return {"type": "blocked", "message": str(exc), "sql": sql}
        except Exception as exc:             # SQL error: let Claude fix it once
            error = str(exc)
            if attempt == 0:
                try:
                    plan = generate_sql(client, question, previous_sql=sql, error=error)
                except AIFormatError:
                    break
                if plan.get("type") != "sql":
                    break
                sql = plan["sql"]
    log(question, "failed", sql)
    return {"type": "error", "message": f"The query failed: {error}", "sql": sql}