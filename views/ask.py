"""Ask the Data: plain-English questions answered with AI-written SQL, shown in full for checking."""
import os

import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv

from ask_engine import MAX_ROWS, MODEL, ask

st.title("💬 Ask the Data")
st.caption(f"Ask a question about cars, sales and profit. Claude ({MODEL}) writes a SQL query, the app checks it "
           f"is read-only, runs it, and shows the answer with the query. Results are capped at {MAX_ROWS:,} rows.")
st.warning("Answers come from AI-written SQL. Check the query before relying on a number for a decision.")


def api_key():
    load_dotenv()
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        try:
            key = st.secrets["ANTHROPIC_API_KEY"]   # used when the app is deployed online
        except Exception:
            key = None
    return key


key = api_key()
if not key:
    st.error("No ANTHROPIC_API_KEY found. Add it to your .env file (locally) or app secrets (online).")
    st.stop()


@st.cache_resource
def get_client(k):
    return Anthropic(api_key=k)


client = get_client(key)
if "chat" not in st.session_state:
    st.session_state["chat"] = []

examples = ["How many cars did we sell in 2025?", "What is the average profit per car by body type?",
            "Which acquisition channel has the highest average profit per car?", "What are our best cars?"]
cols = st.columns(len(examples))
pressed = [c.button(q, width="stretch") for c, q in zip(cols, examples)]   # draw every button first
clicked = next((q for q, p in zip(examples, pressed) if p), None)
question = st.chat_input("Ask a question, or answer a clarifying question") or clicked

if question:
    # If the AI just asked a clarifying question, combine the answer with the original question.
    chat = st.session_state["chat"]
    to_ask = question
    if chat and chat[-1][1]["type"] == "clarify" and not clicked:
        to_ask = f"{chat[-1][1].get('asked', chat[-1][0])}\nClarification: {question}"
    with st.spinner("Writing and checking the query..."):
        try:
            result = ask(client, to_ask)
            result["asked"] = to_ask
        except Exception as exc:
            result = {"type": "error", "message": f"Could not reach the AI service: {exc}"}
    st.session_state["chat"].append((question, result))

for q, r in reversed(st.session_state["chat"]):
    with st.chat_message("user"):
        st.write(q)
    with st.chat_message("assistant"):
        if r["type"] == "answer":
            st.write(r["summary"])
            st.dataframe(r["data"], hide_index=True, width="stretch")
            with st.expander("The SQL behind this answer"):
                st.caption(r["explanation"] + (" (fixed after one failed attempt)" if r["retried"] else ""))
                st.code(r["sql"], language="sql")
        elif r["type"] == "clarify":
            st.info(f"Clarifying question: {r['message']}")
        elif r["type"] == "refuse":
            st.warning(f"Declined: {r['message']}")
        elif r["type"] == "blocked":
            st.error(f"Blocked by the safety check: {r['message']}")
            st.code(r.get("sql", ""), language="sql")
        else:
            st.error(r["message"])
            if r.get("sql"):
                st.code(r["sql"], language="sql")