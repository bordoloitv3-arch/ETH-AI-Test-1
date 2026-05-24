from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd
from backtester.engine import BacktestResult, FuturesBacktester
from memory.sqlite_memory import SQLOptimizationMemory

logger = logging.getLogger(__name__)

try:
    from joblib import Parallel, delayed  # type: ignore
    _JOBLIB_AVAILABLE = True
except ImportError:
    _JOBLIB_AVAILABLE = False


@dataclass
class MonteCarloResult:
    simulation_metrics: pd.DataFrame
    summary: Dict[str, Any]
    sample_equities: List[pd.Series]


def _build_price_dataframe(close_values: np.ndarray, index: Optional[pd.Index] = None) -> pd.DataFrame:
    df = pd.DataFrame({"close": close_values}, index=index)
    df["open"] = df["close"]
    df["high"] = df["close"]
    df["low"] = df["close"]
    return df


def _build_signal_series(signal_values: np.ndarray, index: Optional[pd.Index] = None) -> pd.Series:
    return pd.Series(signal_values, index=index)


def _perturb_price_array(close_values: np.ndarray, rng: np.random.Generator, vol_perturb: float) -> np.ndarray:
    returns = np.zeros_like(close_values, dtype=float)
    if close_values.size > 1:
        returns[1:] = np.diff(close_values) / close_values[:-1]
    scale = rng.normal(1.0, vol_perturb)
    return np.cumprod(1 + returns * scale) * float(close_values[0])


def _perturb_signal_array(signal_values: np.ndarray, rng: np.random.Generator, max_shift: int) -> np.ndarray:
    signals = signal_values.copy()
    if max_shift <= 0 or signals.size == 0:
        return signals

    positions = np.arange(signals.size, dtype=int)
    for index in range(signals.size):
        if signals[index] != 0 and rng.random() < 0.15:
            shift = int(rng.integers(-max_shift, max_shift + 1))
            positions[index] = min(max(0, index + shift), signals.size - 1)

    perturbed = np.zeros_like(signals)
    for src_idx, dest_idx in enumerate(positions):
        perturbed[dest_idx] = signals[src_idx]
    return perturbed


def _run_single_worker(payload: Dict[str, Any]) -> Dict[str, Any]:
    rng = np.random.default_rng(int(payload["seed"]))
    close_values = np.asarray(payload["price_values"], dtype=float)
    signal_values = np.asarray(payload["signal_values"], dtype=float)
    index = payload["index"]

    slippage = float(abs(rng.normal(payload["base_slippage"], payload["base_slippage"] * 0.5)))
    spread = float(abs(rng.normal(payload["base_spread"], payload["base_spread"] * 0.5)))
    fee = float(abs(rng.normal(payload["base_fee"], payload["base_fee"] * 0.3)))
    fill_delay = int(rng.integers(0, max(1, payload["max_delay"] + 1)))

    perturbed_close = _perturb_price_array(close_values, rng, payload["vol_perturb"])
    prices = _build_price_dataframe(perturbed_close, index=index)
    signals = _build_signal_series(_perturb_signal_array(signal_values, rng, max_shift=3), index=index)

    bt_kwargs = dict(payload["backtester_kwargs"])
    bt_kwargs.update(
        {
            "slippage_pct": slippage,
            "spread": spread,
            "fee_rate": fee,
            "fill_delay_bars": fill_delay,
        }
    )
    backtester = FuturesBacktester(prices, **bt_kwargs)
    result: BacktestResult = backtester.run(signals, realistic=True)

    equity = result.equity_curve
    returns = equity.pct_change().dropna()
    sharpe = float((returns.mean() / returns.std()) * (252 ** 0.5)) if not returns.empty and returns.std() > 0 else 0.0
    max_dd = float(np.abs(backtester._max_drawdown(equity))) if not equity.empty else 0.0
    final_balance = float(equity.iloc[-1]) if not equity.empty else float(backtester.initial_balance)

    var95 = float(np.percentile(returns, 5)) if not returns.empty else 0.0
    cvar95 = float(returns[returns <= var95].mean()) if not returns.empty else 0.0

    record = {
        "final_balance": final_balance,
        "return_pct": (final_balance / backtester.initial_balance - 1.0) * 100.0,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "var95": var95,
        "cvar95": cvar95,
        "slippage": slippage,
        "spread": spread,
        "fee": fee,
        "fill_delay": fill_delay,
    }
    if payload.get("save_sample_equity", False):
        record["equity"] = equity
    return record


class MonteCarloEngine:
    """Run institutional-grade Monte Carlo robustness tests for a strategy.

    The engine perturbs execution parameters and price series to produce
    distributions of outcomes used to score robustness.
    """

    def __init__(
        self,
        price_series: pd.Series | pd.DataFrame,
        signals: pd.Series,
        backtester_kwargs: Optional[Dict[str, Any]] = None,
        memory: Optional[SQLOptimizationMemory] = None,
    ) -> None:
        self.price_series = price_series
        self.signals = signals
        self.backtester_kwargs = backtester_kwargs or {}
        self.memory = memory

        if isinstance(price_series, pd.DataFrame):
            if "close" in price_series.columns:
                self.price_values = price_series["close"].to_numpy(dtype=float)
            else:
                self.price_values = price_series.iloc[:, 0].to_numpy(dtype=float)
            self.index = price_series.index
        else:
            self.price_values = price_series.to_numpy(dtype=float)
            self.index = price_series.index

        self.signal_values = signals.to_numpy(dtype=float)

    def _build_payload(
        self,
        seed: int,
        base_slippage: float,
        base_spread: float,
        base_fee: float,
        max_delay: int,
        vol_perturb: float,
        save_sample_equity: bool,
    ) -> Dict[str, Any]:
        return {
            "seed": int(seed),
            "price_values": self.price_values,
            "signal_values": self.signal_values,
            "index": self.index,
            "backtester_kwargs": self.backtester_kwargs,
            "base_slippage": float(base_slippage),
            "base_spread": float(base_spread),
            "base_fee": float(base_fee),
            "max_delay": int(max_delay),
            "vol_perturb": float(vol_perturb),
            "save_sample_equity": save_sample_equity,
        }

    def _build_seeds(self, simulations: int, seed: Optional[int]) -> List[int]:
        if seed is None:
            seed_sequence = np.random.SeedSequence()
        else:
            seed_sequence = np.random.SeedSequence(int(seed))
        return [int(child.generate_state(1)[0]) for child in seed_sequence.spawn(simulations)]

    def _execute_serial(self, payloads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [_run_single_worker(payload) for payload in payloads]

    def _execute_parallel(
        self,
        payloads: List[Dict[str, Any]],
        workers: int,
        backend: str,
        chunk_size: int,
    ) -> List[Dict[str, Any]]:
        backend = backend.lower()
        if backend == "auto":
            backend = "joblib" if _JOBLIB_AVAILABLE else "processpool"

        if backend == "joblib":
            if not _JOBLIB_AVAILABLE:
                raise RuntimeError("joblib backend requested but joblib is not installed")
            return Parallel(n_jobs=workers, backend="loky", batch_size=chunk_size)(
                delayed(_run_single_worker)(payload) for payload in payloads
            )

        if backend in {"processpool", "multiprocessing"}:
            from concurrent.futures import ProcessPoolExecutor

            with ProcessPoolExecutor(max_workers=workers) as executor:
                return list(executor.map(_run_single_worker, payloads, chunksize=chunk_size))

        if backend == "threading":
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=workers) as executor:
                return list(executor.map(_run_single_worker, payloads))

        raise ValueError(f"Unsupported monte carlo backend: {backend}")

    def run(
        self,
        simulations: int = 1000,
        seed: Optional[int] = None,
        base_slippage: float = 0.0005,
        base_spread: float = 0.0,
        base_fee: float = 0.00075,
        max_delay: int = 3,
        vol_perturb: float = 0.2,
        save_folder: Optional[str] = None,
        parallel: bool = False,
        workers: Optional[Union[int, str]] = None,
        chunk_size: int = 100,
        backend: str = "auto",
    ) -> MonteCarloResult:
        workers = workers if workers is not None else "auto"
        if isinstance(workers, str) and workers.lower() == "auto":
            workers = os.cpu_count() or 1
        else:
            workers = max(1, int(workers))

        chunk_size = max(1, int(chunk_size))
        backend = str(backend or "auto")
        parallel_enabled = bool(parallel) and workers > 1

        seeds = self._build_seeds(int(simulations), seed)
        payloads = [
            self._build_payload(
                seed=seeds[i],
                base_slippage=base_slippage,
                base_spread=base_spread,
                base_fee=base_fee,
                max_delay=max_delay,
                vol_perturb=vol_perturb,
                save_sample_equity=i < min(10, int(simulations)),
            )
            for i in range(int(simulations))
        ]

        start_time = time.perf_counter()
        fallback = False
        try:
            if parallel_enabled:
                records = self._execute_parallel(payloads, workers, backend, chunk_size)
            else:
                records = self._execute_serial(payloads)
        except Exception as exc:
            logger.warning(
                "Parallel Monte Carlo execution failed (%s); falling back to serial execution.",
                exc,
                exc_info=True,
            )
            records = self._execute_serial(payloads)
            fallback = True
        end_time = time.perf_counter()

        sample_equities = [record["equity"] for record in records if record.get("equity") is not None]
        records = [{k: v for k, v in record.items() if k != "equity"} for record in records]
        df = pd.DataFrame(records)

        prob_ruin = float((df["final_balance"] <= 0).mean())
        survival_rate = 1.0 - prob_ruin
        ci_lower = float(np.percentile(df["return_pct"], 2.5))
        ci_upper = float(np.percentile(df["return_pct"], 97.5))
        expected_drawdown = float(df["max_drawdown"].mean())
        sharpe_dist = df["sharpe"]

        average_var95 = float(np.mean(df["var95"])) if "var95" in df.columns else 0.0
        average_cvar95 = float(np.mean(df["cvar95"])) if "cvar95" in df.columns else 0.0
        elapsed_seconds = float(end_time - start_time)
        throughput = float(df.shape[0] / elapsed_seconds) if elapsed_seconds > 0 else float(df.shape[0])
        cpu_count = os.cpu_count() or 1
        estimated_cpu_utilization = float(min(1.0, workers / cpu_count)) if parallel_enabled else 0.0

        summary = {
            "simulations": int(simulations),
            "probability_of_ruin": prob_ruin,
            "survival_rate": survival_rate,
            "return_ci_2.5": ci_lower,
            "return_ci_97.5": ci_upper,
            "expected_drawdown": expected_drawdown,
            "average_sharpe_ratio": float(sharpe_dist.mean()),
            "sharpe_std": float(sharpe_dist.std()),
            "average_var95": average_var95,
            "average_cvar95": average_cvar95,
            "parallel": parallel_enabled,
            "backend": backend,
            "worker_count": int(workers),
            "chunk_size": int(chunk_size),
            "cpu_count": int(cpu_count),
            "estimated_cpu_utilization": estimated_cpu_utilization,
            "runtime_seconds": elapsed_seconds,
            "throughput_simulations_per_second": throughput,
            "parallel_fallback": fallback,
        }

        consistency = float(1.0 / (1.0 + float(df["return_pct"].std()))) if df["return_pct"].std() > 0 else 1.0
        drawdown_stability = float(1.0 / (1.0 + float(df["max_drawdown"].std()))) if df["max_drawdown"].std() > 0 else 1.0
        survival_score = survival_rate
        rar_stability = float(1.0 / (1.0 + float(df["sharpe"].std()))) if df["sharpe"].std() > 0 else 1.0

        robustness_score = float((consistency * 0.25) + (drawdown_stability * 0.25) + (survival_score * 0.3) + (rar_stability * 0.2))
        summary["robustness_score"] = robustness_score
        return_std = float(df["return_pct"].std()) if "return_pct" in df.columns else 0.0
        equity_stability_score = float(1.0 / (1.0 + return_std)) if return_std > 0 else 1.0
        summary["equity_stability_score"] = equity_stability_score

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        folder = Path(save_folder or f"reports/monte_carlo_{timestamp}")
        folder.mkdir(parents=True, exist_ok=True)
        csv_path = folder / "simulations.csv"
        json_path = folder / "summary.json"

        df.to_csv(csv_path, index=False)
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(
                {"summary": summary, "head": df.head(50).to_dict(orient="records")},
                fh,
                default=lambda o: str(o),
            )

        if self.memory:
            self.memory.save_run(
                engine="monte_carlo",
                parameters={
                    "simulations": int(simulations),
                    "parallel": parallel_enabled,
                    "workers": int(workers),
                    "backend": backend,
                    "chunk_size": int(chunk_size),
                },
                metrics=summary,
                report_path=str(folder),
                robustness_rank=robustness_score,
            )

        return MonteCarloResult(simulation_metrics=df, summary=summary, sample_equities=sample_equities)
