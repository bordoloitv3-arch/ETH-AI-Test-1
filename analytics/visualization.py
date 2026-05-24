from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


class Visualization:
    @staticmethod
    def plot_equity_curve(equity_curve: pd.Series, output_path: str, title: str = "Equity Curve") -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        plt.figure(figsize=(10, 5))
        plt.plot(equity_curve.index, equity_curve.values, label="Equity")
        plt.title(title)
        plt.xlabel("Time")
        plt.ylabel("Equity")
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.savefig(path, dpi=180)
        plt.close()

    @staticmethod
    def plot_drawdown_curve(equity_curve: pd.Series, output_path: str, title: str = "Drawdown Curve") -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        peak = equity_curve.cummax()
        drawdown = (equity_curve - peak) / peak

        plt.figure(figsize=(10, 5))
        plt.plot(drawdown.index, drawdown.values, label="Drawdown", color="tab:red")
        plt.fill_between(drawdown.index, drawdown.values, color="tab:red", alpha=0.2)
        plt.title(title)
        plt.xlabel("Time")
        plt.ylabel("Drawdown")
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.savefig(path, dpi=180)
        plt.close()

    @staticmethod
    def plot_dual_equity_curves(
        primary_curve: pd.Series,
        secondary_curve: pd.Series,
        primary_label: str,
        secondary_label: str,
        output_path: str,
        title: str = "Equity Curve Comparison",
    ) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        plt.figure(figsize=(10, 5))
        plt.plot(primary_curve.index, primary_curve.values, label=primary_label)
        plt.plot(secondary_curve.index, secondary_curve.values, label=secondary_label, linestyle="--")
        plt.title(title)
        plt.xlabel("Time")
        plt.ylabel("Equity")
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.savefig(path, dpi=180)
        plt.close()

    @staticmethod
    def plot_bar_scores(scores: pd.Series, output_path: str, title: str = "Score by Window") -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        plt.figure(figsize=(10, 5))
        plt.bar(scores.index.astype(str), scores.values, color="tab:blue", alpha=0.75)
        plt.title(title)
        plt.xlabel("Window")
        plt.ylabel("Score")
        plt.xticks(rotation=45, ha="right")
        plt.grid(axis="y")
        plt.tight_layout()
        plt.savefig(path, dpi=180)
        plt.close()

    @staticmethod
    def plot_line_series(series: pd.Series, output_path: str, title: str = "Line Series") -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        plt.figure(figsize=(10, 5))
        plt.plot(series.index, series.values, marker="o")
        plt.title(title)
        plt.xlabel("Index")
        plt.ylabel("Value")
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(path, dpi=180)
        plt.close()

    @staticmethod
    def plot_histogram(values: pd.Series, output_path: str, title: str = "Histogram") -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        plt.figure(figsize=(10, 5))
        plt.hist(values.dropna(), bins=20, color="tab:green", alpha=0.75)
        plt.title(title)
        plt.xlabel("Value")
        plt.ylabel("Frequency")
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(path, dpi=180)
        plt.close()

    @staticmethod
    def plot_correlation_matrix(corr_matrix: pd.DataFrame, output_path: str, title: str = "Correlation Matrix") -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        plt.figure(figsize=(10, 8))
        plt.imshow(corr_matrix, cmap="coolwarm", vmin=-1, vmax=1)
        plt.colorbar(label="Correlation")
        plt.xticks(range(len(corr_matrix.columns)), corr_matrix.columns, rotation=45, ha="right")
        plt.yticks(range(len(corr_matrix.index)), corr_matrix.index)
        plt.title(title)
        plt.tight_layout()
        plt.savefig(path, dpi=180)
        plt.close()

    @staticmethod
    def plot_equity_curve_vectorbt(equity_curve: pd.Series, output_path: str, title: str = "Equity Curve") -> None:
        try:
            import vectorbt as vbt

            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            fig = vbt.plot(equity_curve, title=title)
            fig.write_image(str(path))
        except Exception:
            Visualization.plot_equity_curve(equity_curve, output_path, title)
