from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import altair as alt
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from fpdf import FPDF

from memory.sqlite_memory import SQLOptimizationMemory


def resolve_report_path(report_path: str) -> Path:
    path = Path(report_path)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def load_runs_from_db(limit: int = 50, database_path: str = "memory/optimizer_memory.db") -> List[Dict[str, Any]]:
    memory = SQLOptimizationMemory(database_path)
    try:
        runs = memory.get_runs(limit=limit)
    finally:
        memory.close()
    return runs


def load_report_payload(report_path: str) -> Dict[str, Any]:
    path = resolve_report_path(report_path)
    if not path.exists():
        raise FileNotFoundError(f"Report JSON not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_series(data: Any) -> pd.Series:
    if isinstance(data, pd.Series):
        return data.reset_index(drop=True)
    if isinstance(data, list):
        return pd.Series(data)
    if isinstance(data, np.ndarray):
        return pd.Series(data.tolist())
    return pd.Series([data])


def compute_drawdown(equity: pd.Series) -> pd.Series:
    equity = normalize_series(equity).astype(float)
    running_max = equity.cummax()
    return (equity - running_max) / running_max


def build_run_table(runs: List[Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for run in runs:
        metrics = run.get("metrics", {}) or {}
        oos_metrics = run.get("oos_metrics") or {}
        rejected = run.get("rejected_parameters") or []
        rows.append(
            {
                "id": run.get("id"),
                "engine": run.get("engine"),
                "created_at": run.get("created_at"),
                "sharpe_ratio": metrics.get("sharpe_ratio"),
                "net_profit": metrics.get("net_profit"),
                "drawdown": metrics.get("drawdown"),
                "robustness_rank": run.get("robustness_rank"),
                "probability_of_ruin": metrics.get("probability_of_ruin") or (run.get("monte_carlo") or {}).get("probability_of_ruin"),
                "oos_sharpe": oos_metrics.get("sharpe_ratio"),
                "stability_rank": metrics.get("equity_stability_score"),
                "rejected": bool(rejected),
                "report_path": run.get("report_path"),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    return df


def build_history_table(history: List[Dict[str, Any]]) -> pd.DataFrame:
    if not history:
        return pd.DataFrame()
    records: List[Dict[str, Any]] = []
    for entry in history:
        row = {"objective": entry.get("value", 0.0)}
        row.update(entry.get("params", {}) or {})
        for field in ["sharpe_ratio", "net_profit", "drawdown", "robustness_score", "probability_of_ruin", "stability_rank", "oos_sharpe"]:
            if field in entry:
                row[field] = entry[field]
        records.append(row)
    return pd.DataFrame(records)


def build_quantile_bands(sample_equities: List[Any]) -> pd.DataFrame:
    series_list = [normalize_series(equity).astype(float) for equity in sample_equities if equity is not None]
    if not series_list:
        return pd.DataFrame()
    long_series = pd.DataFrame(series_list).transpose().fillna(method="ffill", axis=0).fillna(method="bfill", axis=0)
    bands = {
        "index": long_series.index,
        "p10": np.percentile(long_series, 10, axis=1),
        "p25": np.percentile(long_series, 25, axis=1),
        "median": np.percentile(long_series, 50, axis=1),
        "p75": np.percentile(long_series, 75, axis=1),
        "p90": np.percentile(long_series, 90, axis=1),
    }
    return pd.DataFrame(bands)


def build_trade_overview(trades: List[Dict[str, Any]]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    if "entry_price" in df.columns and "exit_price" in df.columns:
        df["return_pct"] = df["return_pct"].astype(float)
    return df


def summarize_trades(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {}
    wins = df[df["pnl"] > 0]
    losses = df[df["pnl"] <= 0]
    return {
        "total_trades": int(len(df)),
        "win_rate": float(len(wins) / len(df)) if len(df) > 0 else 0.0,
        "avg_return_pct": float(df["return_pct"].mean()) if "return_pct" in df.columns else None,
        "avg_win": float(wins["pnl"].mean()) if not wins.empty else 0.0,
        "avg_loss": float(losses["pnl"].mean()) if not losses.empty else 0.0,
    }


def generate_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def generate_json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, default=str).encode("utf-8")


def generate_pdf_report_bytes(report_title: str, run: Dict[str, Any], report_data: Dict[str, Any]) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, report_title, ln=True)
    pdf.set_font("Arial", size=11)
    pdf.ln(4)

    summary_metrics = report_data.get("metrics", {})
    pdf.cell(0, 8, "Summary Metrics", ln=True)
    for key, value in summary_metrics.items():
        pdf.cell(0, 6, f"{key}: {value}", ln=True)
    pdf.ln(4)

    oos_metrics = report_data.get("oos_metrics") or {}
    if oos_metrics:
        pdf.cell(0, 8, "OOS Validation Metrics", ln=True)
        for key, value in oos_metrics.items():
            pdf.cell(0, 6, f"{key}: {value}", ln=True)
        pdf.ln(4)

    monte_carlo = report_data.get("monte_carlo") or {}
    if monte_carlo:
        pdf.cell(0, 8, "Monte Carlo Summary", ln=True)
        for key, value in monte_carlo.items():
            if key in {"sample_equities"}:
                continue
            pdf.cell(0, 6, f"{key}: {value}", ln=True)
        pdf.ln(4)

    rejected = report_data.get("rejected_parameters") or []
    if rejected:
        pdf.cell(0, 8, "Rejected Strategies", ln=True)
        for entry in rejected[:3]:
            pdf.multi_cell(0, 6, json.dumps(entry, default=str))
        pdf.ln(4)

    content = pdf.output(dest="S")
    return content.encode("latin-1")


def render_equity_curve_png(equity: pd.Series) -> bytes:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(equity.index, equity.values, color="#1f77b4", linewidth=2)
    ax.set_title("Equity Curve")
    ax.set_xlabel("Index")
    ax.set_ylabel("Equity")
    ax.grid(True, alpha=0.3)
    buffer = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)
    return buffer.getvalue()


def render_drawdown_png(drawdown: pd.Series) -> bytes:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.fill_between(drawdown.index, drawdown.values, 0, color="#d62728", alpha=0.4)
    ax.set_title("Drawdown Curve")
    ax.set_xlabel("Index")
    ax.set_ylabel("Drawdown")
    ax.grid(True, alpha=0.3)
    buffer = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)
    return buffer.getvalue()


def build_correlation_heatmap(df: pd.DataFrame) -> alt.Chart:
    numeric = df.select_dtypes(include="number")
    if numeric.shape[1] < 2:
        raise ValueError("Not enough numeric parameters for heatmap")
    corr = numeric.corr().reset_index().melt(id_vars="index")
    corr.columns = ["x", "y", "correlation"]
    return (
        alt.Chart(corr)
        .mark_rect()
        .encode(
            x=alt.X("x:N", title="Parameter"),
            y=alt.Y("y:N", title="Parameter"),
            color=alt.Color("correlation:Q", scale=alt.Scale(scheme="viridis")),
            tooltip=["x", "y", "correlation"],
        )
        .properties(width=700, height=500)
    )


def build_line_chart(series: pd.Series, title: str, y_label: str = "Value") -> alt.Chart:
    df = pd.DataFrame({"index": series.index, y_label: series.values})
    return (
        alt.Chart(df)
        .mark_line(point=False)
        .encode(x=alt.X("index:T", title="Index"), y=alt.Y(f"{y_label}:Q", title=y_label), tooltip=["index", f"{y_label}:Q"])
        .properties(width=700, height=360, title=title)
    )


def build_histogram(series: pd.Series, title: str, bins: int = 40) -> alt.Chart:
    df = pd.DataFrame({"value": series.dropna().astype(float)})
    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            alt.X("value:Q", bin=alt.Bin(maxbins=bins), title=title),
            y=alt.Y("count():Q", title="Count"),
            tooltip=["count():Q"],
        )
        .properties(width=700, height=360, title=title)
    )


def build_percentile_band_chart(bands: pd.DataFrame, title: str) -> alt.Chart:
    base = pd.DataFrame({"index": bands["index"], "median": bands["median"], "p25": bands["p25"], "p75": bands["p75"], "p10": bands["p10"], "p90": bands["p90"]})
    long = base.melt(id_vars=["index"], value_vars=["p10", "p25", "median", "p75", "p90"], var_name="quantile", value_name="value")
    return (
        alt.Chart(long)
        .mark_line()
        .encode(
            x=alt.X("index:T", title="Index"),
            y=alt.Y("value:Q", title="Equity"),
            color=alt.Color("quantile:N", title="Percentile"),
            tooltip=["index", "quantile", "value"],
        )
        .properties(width=700, height=400, title=title)
    )
