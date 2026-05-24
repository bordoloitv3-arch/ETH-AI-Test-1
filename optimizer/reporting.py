import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from analytics.visualization import Visualization
from utils.types import TradeRecord


class ReportGenerator:
    def __init__(self, output_dir: str = "reports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_csv(self, trades: List[TradeRecord], metrics: Dict[str, Any], report_name: str) -> str:
        report_file = self.output_dir / f"{report_name}.csv"
        records = [trade.__dict__ for trade in trades]
        df = pd.DataFrame.from_records(records)
        df.to_csv(report_file, index=False)

        metrics_file = self.output_dir / f"{report_name}_metrics.csv"
        with metrics_file.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["metric", "value"])
            for key, value in metrics.items():
                writer.writerow([key, value])

        return str(report_file)

    def generate_json(
        self,
        trades: List[TradeRecord],
        metrics: Dict[str, Any],
        report_name: str,
        equity_curve: Optional[Any] = None,
        dataset_metrics: Optional[Dict[str, Any]] = None,
        dataset_equity: Optional[Dict[str, Any]] = None,
        monte_carlo: Optional[Dict[str, Any]] = None,
        optimization_history: Optional[List[Dict[str, Any]]] = None,
        rejected_parameters: Optional[List[Dict[str, Any]]] = None,
        best_parameters: Optional[Dict[str, Any]] = None,
        oos_metrics: Optional[Dict[str, Any]] = None,
        walk_forward_results: Optional[Dict[str, Any]] = None,
    ) -> str:
        report_file = self.output_dir / f"{report_name}.json"
        payload = {
            "metrics": metrics,
            "equity_curve": list(equity_curve) if equity_curve is not None else None,
            "trades": [trade.__dict__ for trade in trades],
            "dataset_metrics": dataset_metrics or {},
            "dataset_equity": {k: list(v) for k, v in (dataset_equity or {}).items()},
            "monte_carlo": monte_carlo or {},
            "optimization_history": optimization_history or [],
            "rejected_parameters": rejected_parameters or [],
            "best_parameters": best_parameters or {},
            "oos_metrics": oos_metrics or {},
            "walk_forward_results": walk_forward_results or {},
        }
        with report_file.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str)
        return str(report_file)

    def generate_summary_csv(self, metrics: Dict[str, Any], dataset_metrics: Dict[str, Any], report_name: str) -> str:
        csv_path = self.output_dir / f"{report_name}_dataset_metrics.csv"
        summary_rows: List[Dict[str, Any]] = [
            {"dataset": "train", **metrics},
        ]
        if dataset_metrics.get("validation"):
            summary_rows.append({"dataset": "validation", **dataset_metrics["validation"]})
        if dataset_metrics.get("test"):
            summary_rows.append({"dataset": "test", **dataset_metrics["test"]})
        df = pd.DataFrame(summary_rows)
        df.to_csv(csv_path, index=False)
        return str(csv_path)

    def generate_parameter_heatmap(self, history: Optional[List[Dict[str, Any]]], report_name: str) -> Optional[str]:
        if not history:
            return None

        raw_rows: List[Dict[str, Any]] = []
        for entry in history:
            row = {**entry.get("params", {}), "score": entry.get("value", 0.0)}
            raw_rows.append(row)

        df = pd.DataFrame(raw_rows)
        numeric = df.select_dtypes(include="number")
        if numeric.shape[1] < 2:
            return None

        corr = numeric.corr()
        plot_path = self.output_dir / f"{report_name}_parameter_heatmap.png"
        Visualization.plot_correlation_matrix(corr, str(plot_path), title="Parameter Heatmap")
        return str(plot_path)

    def generate_parameter_report(self, parameters: List[Any], report_name: str) -> Dict[str, str]:
        parameter_records = [param.to_dict() for param in parameters]
        csv_path = self.output_dir / f"{report_name}.csv"
        json_path = self.output_dir / f"{report_name}.json"

        pd.DataFrame(parameter_records).to_csv(csv_path, index=False)
        with json_path.open("w", encoding="utf-8") as handle:
            json.dump(parameter_records, handle, indent=2)

        return {"csv": str(csv_path), "json": str(json_path)}

    def generate_parameter_metrics_report(
        self,
        optimization_history: List[Dict[str, Any]],
        best_parameters: Optional[Dict[str, Any]],
        oos_metrics: Optional[Dict[str, Any]],
        report_name: str,
    ) -> Dict[str, str]:
        rows: List[Dict[str, Any]] = []
        for entry in optimization_history:
            row = {**entry.get("params", {}), "objective_value": entry.get("value", 0.0)}
            row["is_best"] = entry.get("params", {}) == (best_parameters or {})
            rows.append(row)

        df = pd.DataFrame(rows)
        if best_parameters and oos_metrics:
            for field in ["oos_sharpe_ratio", "oos_drawdown", "oos_net_profit"]:
                df[field] = None
            mask = df["is_best"] == True
            if mask.any():
                best_idx = df[mask].index[0]
                df.at[best_idx, "oos_sharpe_ratio"] = oos_metrics.get("sharpe_ratio")
                df.at[best_idx, "oos_drawdown"] = oos_metrics.get("drawdown")
                df.at[best_idx, "oos_net_profit"] = oos_metrics.get("net_profit")

        csv_path = self.output_dir / f"{report_name}_parameter_metrics.csv"
        json_path = self.output_dir / f"{report_name}_parameter_metrics.json"

        df.to_csv(csv_path, index=False)
        with json_path.open("w", encoding="utf-8") as handle:
            json.dump(df.to_dict(orient="records"), handle, indent=2, default=str)

        return {"csv": str(csv_path), "json": str(json_path)}

    def plot_oos_comparison(self, equity_curve: Any, oos_equity: Any, report_name: str) -> str:
        plot_path = self.output_dir / f"{report_name}_oos_comparison.png"
        Visualization.plot_dual_equity_curves(
            equity_curve,
            oos_equity,
            "In-Sample",
            "Out-of-Sample",
            str(plot_path),
            title="In-Sample vs Out-of-Sample Equity",
        )
        return str(plot_path)

    def plot_walk_forward_scores(self, walk_forward_results: Dict[str, Any], report_name: str) -> Optional[str]:
        if not walk_forward_results or "window_results" not in walk_forward_results:
            return None
        scores = [window.get("score", 0.0) for window in walk_forward_results["window_results"]]
        if not scores:
            return None
        series = pd.Series(scores, index=[window.get("window_index") for window in walk_forward_results["window_results"]])
        plot_path = self.output_dir / f"{report_name}_walk_forward.png"
        Visualization.plot_bar_scores(series, str(plot_path), title="Walk-Forward Window Scores")
        return str(plot_path)

    def plot_optimization_convergence(self, optimization_history: List[Dict[str, Any]], report_name: str) -> Optional[str]:
        if not optimization_history:
            return None
        values = [entry.get("value", 0.0) for entry in optimization_history]
        series = pd.Series(values)
        plot_path = self.output_dir / f"{report_name}_convergence.png"
        Visualization.plot_line_series(series, str(plot_path), title="Optimization Convergence")
        return str(plot_path)

    def plot_robustness_distribution(self, optimization_history: List[Dict[str, Any]], report_name: str) -> Optional[str]:
        if not optimization_history:
            return None
        values = [entry.get("value", 0.0) for entry in optimization_history]
        series = pd.Series(values)
        plot_path = self.output_dir / f"{report_name}_robustness_distribution.png"
        Visualization.plot_histogram(series, str(plot_path), title="Robustness Distribution")
        return str(plot_path)

    def plot_equity_curve(self, equity_curve: Any, report_name: str) -> str:
        plot_path = self.output_dir / f"{report_name}_equity.png"
        Visualization.plot_equity_curve(equity_curve, str(plot_path))
        return str(plot_path)

    def generate_drawdown_chart(self, equity_curve: Any, report_name: str) -> str:
        plot_path = self.output_dir / f"{report_name}_drawdown.png"
        Visualization.plot_drawdown_curve(equity_curve, str(plot_path))
        return str(plot_path)

    def build_report(
        self,
        trades: List[TradeRecord],
        metrics: Dict[str, Any],
        equity_curve: Any,
        report_prefix: str,
        formats: List[str],
        search_history: Optional[List[Dict[str, Any]]] = None,
        dataset_metrics: Optional[Dict[str, Any]] = None,
        dataset_equity: Optional[Dict[str, Any]] = None,
        monte_carlo: Optional[Dict[str, Any]] = None,
        walk_forward_results: Optional[Dict[str, Any]] = None,
        rejected_parameters: Optional[List[Dict[str, Any]]] = None,
        best_parameters: Optional[Dict[str, Any]] = None,
        oos_metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        output: Dict[str, str] = {}
        if "csv" in formats:
            output["csv"] = self.generate_csv(trades, metrics, report_prefix)
            if search_history:
                history_report = self.generate_parameter_metrics_report(search_history, best_parameters, oos_metrics, report_prefix)
                output["parameter_metrics_csv"] = history_report["csv"]
            if dataset_metrics is not None:
                output["dataset_metrics_csv"] = self.generate_summary_csv(metrics, dataset_metrics, report_prefix)
        if "json" in formats:
            output["json"] = self.generate_json(
                trades,
                metrics,
                report_prefix,
                equity_curve=equity_curve,
                dataset_metrics=dataset_metrics,
                dataset_equity=dataset_equity,
                monte_carlo=monte_carlo,
                optimization_history=search_history,
                rejected_parameters=rejected_parameters,
                best_parameters=best_parameters,
                oos_metrics=oos_metrics,
                walk_forward_results=walk_forward_results,
            )
        if "plot" in formats:
            output["plot"] = self.plot_equity_curve(equity_curve, report_prefix)
            output["drawdown_plot"] = self.generate_drawdown_chart(equity_curve, report_prefix)
            if dataset_equity and "test" in dataset_equity:
                output["oos_comparison_plot"] = self.plot_oos_comparison(equity_curve, dataset_equity["test"], report_prefix)
            if walk_forward_results:
                walk_forward_path = self.plot_walk_forward_scores(walk_forward_results, report_prefix)
                if walk_forward_path:
                    output["walk_forward_plot"] = walk_forward_path
            if search_history:
                convergence_path = self.plot_optimization_convergence(search_history, report_prefix)
                if convergence_path:
                    output["convergence_plot"] = convergence_path
                robustness_path = self.plot_robustness_distribution(search_history, report_prefix)
                if robustness_path:
                    output["robustness_plot"] = robustness_path
                heatmap_path = self.generate_parameter_heatmap(search_history, report_prefix)
                if heatmap_path:
                    output["heatmap"] = heatmap_path
        return output
