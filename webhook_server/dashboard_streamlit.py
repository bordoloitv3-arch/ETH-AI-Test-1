import sqlite3
import streamlit as st

DB_PATH = st.sidebar.text_input("DB Path", "webhook_state.db")

@st.cache_data
def read_table(query: str, db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    df = None
    try:
        import pandas as pd
        df = pd.read_sql_query(query, conn)
    finally:
        conn.close()
    return df

st.title("Webhook - Paper Trading Dashboard")

alerts = read_table("SELECT * FROM alerts ORDER BY received_at DESC LIMIT 200", DB_PATH)
executions = read_table("SELECT * FROM executions ORDER BY created_at DESC LIMIT 200", DB_PATH)
metrics = read_table("SELECT * FROM metrics ORDER BY created_at DESC LIMIT 200", DB_PATH)
errors = read_table("SELECT * FROM errors ORDER BY created_at DESC LIMIT 200", DB_PATH)

st.header("Recent Alerts")
st.dataframe(alerts)

st.header("Executions")
st.dataframe(executions)

st.header("Metrics")
st.dataframe(metrics)

st.header("Errors")
st.dataframe(errors)
