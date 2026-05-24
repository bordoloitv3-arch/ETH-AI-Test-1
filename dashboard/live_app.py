from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import altair as alt
import pandas as pd
import streamlit as st

from dashboard.utils import build_line_chart, normalize_series


def _format_live_rows(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df


def _load_webhook_state() -> Dict[str, Any]:
    path = Path("reports/webhook/webhook_state.json")
    if not path.exists():
        return {}
    try:
        import json

        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def render_live_monitoring(report: Dict[str, Any]) -> None:
    st.header("Live Monitoring")
    state = report.get("live_state") or report.get("engine_state") or {}
    if not state:
        state = _load_webhook_state().get("engine_state", {})
    if not state:
        st.info("No live streaming state is available. Load a live report or run a replay session to view monitoring metrics.")
        return

    cols = st.columns(3)
    cols[0].metric("Balance", f"${state.get('balance', 0.0):,.2f}")
    cols[0].metric("Equity", f"${state.get('equity', 0.0):,.2f}")
    cols[1].metric("Open Positions", len(state.get("positions", [])))
    cols[1].metric("Open Orders", len(state.get("open_orders", [])))
    cols[2].metric("Emergency Stop", state.get("emergency_stopped", False))
    cols[2].metric("Max Drawdown", f"{state.get('drawdown', 0.0):.2%}")

    st.subheader("Live Equity Curve")
    equity_curve = normalize_series(state.get("equity_curve", []))
    if not equity_curve.empty:
        st.altair_chart(build_line_chart(equity_curve, "Live Equity Curve", y_label="Equity"), use_container_width=True)
    else:
        st.info("Equity curve data is not available yet.")

    st.subheader("Open Positions")
    positions = _format_live_rows(state.get("positions", []))
    if not positions.empty:
        st.dataframe(positions, use_container_width=True)
    else:
        st.write("No open positions at this time.")

    st.subheader("Open Orders")
    orders = _format_live_rows(state.get("open_orders", []))
    if not orders.empty:
        st.dataframe(orders, use_container_width=True)
    else:
        st.write("No open orders at this time.")

    st.subheader("Execution Log")
    log = _format_live_rows(state.get("execution_log", [])[-25:])
    if not log.empty:
        st.dataframe(log.sort_values(by="timestamp", ascending=False), use_container_width=True)
    else:
        st.write("No executions yet.")

    st.subheader("Latency Metrics")
    latency = normalize_series(state.get("latency_history", []))
    if not latency.empty:
        st.write(f"Average latency: {float(latency.mean()):.1f} ms")
        st.write(f"Max latency: {float(latency.max()):.1f} ms")
    else:
        st.write("Latency metrics are not available.")

    if report.get("connection_status") is not None:
        st.subheader("Connection Status")
        st.write(f"Status: {report.get('connection_status')}")
        st.write(f"Reconnect attempts: {report.get('reconnect_count')}")
        st.write(f"Stream URL: {report.get('stream_url')}")
