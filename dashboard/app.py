from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import altair as alt
import pandas as pd
import streamlit as st

from dashboard.utils import (
    build_correlation_heatmap,
    build_history_table,
    build_monte_carlo_bands,
    build_run_table,
    build_trade_overview,
    compute_drawdown,
    generate_csv_bytes,
    generate_json_bytes,
    generate_pdf_report_bytes,
    load_report_payload,
    load_runs_from_db,
    normalize_series,
    render_drawdown_png,
    render_equity_curve_png,
)
from dashboard.live_app import render_live_monitoring


@st.cache_data(show_spinner=False)
def get_runs(limit: int = 50) -> List[Dict[str, Any]]:
    return load_runs_from_db(limit=limit)


@st.cache_data(show_spinner=False)
def get_report_payload(report_path: str) -> Dict[str, Any]:
    return load_report_payload(report_path)


def select_data_source() -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    source = st.sidebar.radio("Report source", ["SQLite memory", "Upload JSON"])
    runs: List[Dict[str, Any]] = []
    selected: Optional[Dict[str, Any]] = None

    if source == "SQLite memory":
        limit = st.sidebar.slider("Runs to load", min_value=10, max_value=200, value=50, step=10)
        runs = get_runs(limit)
        if runs:
            run_options = [f"#{run['id']} - {run['engine']} @ {run['created_at']}" for run in runs]
            selected_label = st.sidebar.selectbox("Select a saved run", run_options)
            selected = runs[run_options.index(selected_label)]
        else:
            st.sidebar.warning("No optimization runs found in SQLite memory.")
    else:
        upload = st.sidebar.file_uploader("Upload report JSON", type=["json"])
        if upload is not None:
            report_data = json.load(upload)
            selected = {
                "id": 0,
                "engine": report_data.get("best_parameters", {}).get("engine", "unknown"),
                "created_at": "uploaded",
                "parameters": report_data.get("best_parameters", {}),
                "metrics": report_data.get("metrics", {}),
                "report_path": "uploaded",
                "optimization_history": report_data.get("optimization_history", []),
                "rejected_parameters": report_data.get("rejected_parameters", []),
                "oos_metrics": report_data.get("oos_metrics", {}),
                "walk_forward_metrics": report_data.get("walk_forward_results", {}),
            }
            runs = [selected]
    return selected, runs


def render_metrics(summary: Dict[str, Any], label: str = "") -> None:
    if not summary:
        st.write("No metrics available.")
        return
    cols = st.columns(4)
    metrics = [
        ("Sharpe", summary.get("sharpe_ratio") or summary.get("average_sharpe_ratio")),
        ("Net Profit", summary.get("net_profit") or summary.get("return_pct")),
        ("Drawdown", summary.get("drawdown") or summary.get("expected_drawdown")),
        ("Robustness", summary.get("robustness_rank") or summary.get("robustness_score")),
    ]
    for col, (name, value) in zip(cols, metrics):
        col.metric(name, f"{value:.4f}" if isinstance(value, (int, float)) else value)
    extra_cols = st.columns(3)
    extra_metrics = [
        ("POWR", summary.get("probability_of_ruin")),
        ("OOS Sharpe", summary.get("sharpe_ratio") if label == "OOS" else None),
        ("Stability", summary.get("equity_stability_score")),
    ]
    for col, (name, value) in zip(extra_cols, extra_metrics):
        col.metric(name, f"{value:.4f}" if isinstance(value, (int, float)) else value)


def render_overview(run: Dict[str, Any], report: Optional[Dict[str, Any]]) -> None:
    st.header("Optimization Overview")
    if report:
        st.write(f"**Report Path:** {run.get('report_path')}" )
    st.write(f"**Engine:** {run.get('engine')}")
    st.write(f"**Created At:** {run.get('created_at')}")
    summary = report.get("metrics") if report else run.get("metrics", {})
    render_metrics(summary)
    if report and report.get("best_parameters"):
        with st.expander("Selected parameters"):
            st.json(report.get("best_parameters"))


def render_best_rankings(report: Optional[Dict[str, Any]]) -> None:
    st.header("Best Strategy Rankings")
    history = report.get("optimization_history") if report else []
    if not history:
        st.warning("No optimization history available for this run.")
        return
    df = build_history_table(history)
    if df.empty:
        st.warning("Optimization entries do not contain numeric parameters.")
        return
    st.dataframe(df.sort_values("objective", ascending=False), use_container_width=True)


def render_monte_carlo(report: Optional[Dict[str, Any]]) -> None:
    st.header("Monte Carlo Analysis")
    mc = report.get("monte_carlo") if report else {}
    if not mc:
        st.info("Monte Carlo summary not available for this run.")
        return
    st.json(mc)
    sample_equities = mc.get("sample_equities") or []
    if sample_equities:
        bands = build_monte_carlo_bands(sample_equities)
        chart = alt.Chart(bands).transform_fold(
            ["p10", "p25", "median", "p75", "p90"],
            as_=["quantile", "equity"],
        ).mark_line().encode(
            x=alt.X("index:Q", title="Bar index"),
            y=alt.Y("equity:Q", title="Equity"),
            color="quantile:N",
            tooltip=["index", "quantile", "equity"],
        ).properties(width=900, height=420, title="Monte Carlo Percentile Bands")
        st.altair_chart(chart, use_container_width=True)


def render_walk_forward(report: Optional[Dict[str, Any]]) -> None:
    st.header("Walk-Forward Analysis")
    wf = report.get("walk_forward_results") if report else {}
    if not wf:
        st.info("No walk-forward results available.")
        return
    st.json(wf)
    window_results = wf.get("window_results") or []
    if window_results:
        df = pd.DataFrame(window_results)
        st.dataframe(df)
        if "score" in df.columns:
            chart = alt.Chart(df).mark_line(point=True).encode(
                x=alt.X("window_index:O", title="Window"),
                y=alt.Y("score:Q", title="Score"),
                tooltip=["window_index", "score"],
            ).properties(width=900, height=360)
            st.altair_chart(chart, use_container_width=True)


def render_oos(report: Optional[Dict[str, Any]]) -> None:
    st.header("Out-of-Sample Validation")
    dataset_metrics = report.get("dataset_metrics") if report else {}
    if not dataset_metrics:
        st.info("No dataset metrics available.")
        return
    st.json(dataset_metrics)
    if dataset_metrics.get("test"):
        st.subheader("Test Metrics")
        render_metrics(dataset_metrics.get("test"), label="OOS")


def render_rejections(report: Optional[Dict[str, Any]]) -> None:
    st.header("Rejected Strategy Analysis")
    rejected = report.get("rejected_parameters") if report else []
    if not rejected:
        st.info("No rejected strategies recorded for this run.")
        return
    normalized = pd.json_normalize(rejected)
    st.dataframe(normalized, use_container_width=True)


def render_heatmap(report: Optional[Dict[str, Any]]) -> None:
    st.header("Parameter Heatmap")
    history = report.get("optimization_history") if report else []
    df = build_history_table(history)
    if df.empty:
        st.info("No parameter history available for heatmap.")
        return
    try:
        chart = build_correlation_heatmap(df)
        st.altair_chart(chart, use_container_width=True)
    except ValueError as exc:
        st.warning(str(exc))


def render_trades(report: Optional[Dict[str, Any]]) -> None:
    st.header("Trade Analytics")
    trades = report.get("trades") if report else []
    if not trades:
        st.info("No trade logs available.")
        return
    df = build_trade_overview(trades)
    stats = build_trade_overview(trades)
    st.write(f"Total trades: {len(df)}")
    if not df.empty and "return_pct" in df.columns:
        st.write(f"Win rate: {float((df['pnl'] > 0).sum() / len(df)):.2%}")
        st.write(f"Average return: {float(df['return_pct'].mean()):.2%}")
    st.dataframe(df, use_container_width=True)


def render_comparison(selected_runs: List[Dict[str, Any]]) -> None:
    st.header("Comparison Mode")
    if len(selected_runs) < 2:
        st.info("Choose two or more runs to compare side-by-side.")
        return
    rows = []
    for run in selected_runs:
        report = run.get("report") or {}
        metrics = report.get("metrics") or run.get("metrics") or {}
        rows.append(
            {
                "id": run.get("id"),
                "engine": run.get("engine"),
                "created_at": run.get("created_at"),
                "sharpe_ratio": metrics.get("sharpe_ratio"),
                "net_profit": metrics.get("net_profit"),
                "drawdown": metrics.get("drawdown"),
                "robustness_score": report.get("monte_carlo", {}).get("robustness_score"),
                "probability_of_ruin": report.get("monte_carlo", {}).get("probability_of_ruin"),
                "oos_sharpe": report.get("oos_metrics", {}).get("sharpe_ratio"),
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(df.set_index("id"), use_container_width=True)


def render_exports(run: Dict[str, Any], report: Optional[Dict[str, Any]]) -> None:
    st.header("Export Reports")
    if not report:
        st.info("No report payload to export.")
        return
    if report.get("trades"):
        trade_df = build_trade_overview(report["trades"])
        csv_bytes = generate_csv_bytes(trade_df)
        st.download_button("Export trades CSV", csv_bytes, file_name=f"trade_log_run_{run.get('id')}.csv", mime="text/csv")
    json_bytes = generate_json_bytes(report)
    st.download_button("Export JSON report", json_bytes, file_name=f"strategy_report_{run.get('id')}.json", mime="application/json")
    pdf_bytes = generate_pdf_report_bytes(f"Run {run.get('id')} Summary", run, report)
    st.download_button("Export PDF summary", pdf_bytes, file_name=f"strategy_summary_{run.get('id')}.pdf", mime="application/pdf")
    if report.get("equity_curve"):
        equity = normalize_series(report["equity_curve"])
        png_equity = render_equity_curve_png(equity)
        st.download_button("Export equity curve PNG", png_equity, file_name=f"equity_curve_{run.get('id')}.png", mime="image/png")
        drawdown = compute_drawdown(equity)
        png_drawdown = render_drawdown_png(drawdown)
        st.download_button("Export drawdown PNG", png_drawdown, file_name=f"drawdown_{run.get('id')}.png", mime="image/png")


def main() -> None:
    st.set_page_config(page_title="Quant Research Dashboard", layout="wide")
    st.title("Quantitative Research Dashboard")
    st.markdown("A modular Streamlit UI for optimization, Monte Carlo analysis, OOS validation, and candidate comparison.")

    selected_run, runs = select_data_source()
    if not selected_run:
        st.stop()

    report: Optional[Dict[str, Any]] = None
    if selected_run.get("report_path") and selected_run["report_path"] != "uploaded":
        try:
            report = get_report_payload(selected_run["report_path"])
        except FileNotFoundError:
            st.warning("Report JSON path could not be loaded. Dashboard will show available saved metadata only.")
    if selected_run["report_path"] == "uploaded":
        report = selected_run

    compare_mode = st.sidebar.checkbox("Enable comparison mode")
    selected_compare_ids: List[int] = []
    if compare_mode and runs:
        selection = st.sidebar.multiselect(
            "Select runs to compare",
            [run.get("id") for run in runs],
            default=[runs[0].get("id")],
        )
        selected_compare_ids = [int(value) for value in selection]

    if compare_mode and selected_compare_ids:
        selected_compare_runs = [run for run in runs if run.get("id") in selected_compare_ids]
        for run in selected_compare_runs:
            if run.get("report_path") and run["report_path"] != "uploaded":
                try:
                    run["report"] = get_report_payload(run["report_path"])
                except FileNotFoundError:
                    run["report"] = None
        render_comparison(selected_compare_runs)
    else:
        tabs = st.tabs([
            "Overview",
            "Best Rankings",
            "Monte Carlo",
            "Walk-Forward",
            "OOS Validation",
            "Rejected Strategies",
            "Parameter Heatmap",
            "Trade Analytics",
            "Live Monitoring",
            "Export",
        ])
        with tabs[0]:
            render_overview(selected_run, report)
        with tabs[1]:
            render_best_rankings(report)
        with tabs[2]:
            render_monte_carlo(report)
        with tabs[3]:
            render_walk_forward(report)
        with tabs[4]:
            render_oos(report)
        with tabs[5]:
            render_rejections(report)
        with tabs[6]:
            render_heatmap(report)
        with tabs[7]:
            render_trades(report)
        with tabs[8]:
            render_live_monitoring(report or selected_run)
        with tabs[9]:
            render_exports(selected_run, report)

    if runs:
        st.sidebar.markdown("### Loaded Runs")
        run_table = build_run_table(runs)
        st.sidebar.dataframe(run_table.sort_values(["created_at"], ascending=False).head(10))


if __name__ == "__main__":
    main()
