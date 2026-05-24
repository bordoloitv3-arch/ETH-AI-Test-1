from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from live.paper_engine import PaperTradingEngine
from live.replay import MarketReplay


RegimeType = str
SignalCallback = Callable[[pd.Series, PaperTradingEngine], Any]


DEFAULT_REGIME_THRESHOLDS = {
    "trend_pct": 0.015,
    "low_volatility": 0.005,
    "high_volatility": 0.02,
}


@dataclass
class ValidationSessionResult:
    session_name: str
    start_time: datetime
    end_time: datetime
    metrics: Dict[str, Any]
    regime_metrics: Dict[str, Any]
    daily_summary: List[Dict[str, Any]]
    weekly_summary: List[Dict[str, Any]]
    alerts: List[str]
    drift_report: Dict[str, Any]
    health_history: List[Dict[str, Any]]
    execution_quality_history: List[Dict[str, Any]]
    regime_map: Dict[str, RegimeType] = field(default_factory=dict)
    equity_curve: List[float] = field(default_factory=list)
    equity_timestamps: List[str] = field(default_factory=list)


class LiveValidationSession:
    def __init__(
        self,
        session_name: str,
        candles: pd.DataFrame,
        engine: PaperTradingEngine,
        signal_source: Optional[Union[pd.Series, Dict[datetime, Any], SignalCallback]] = None,
        baseline_metrics: Optional[Dict[str, Any]] = None,
        regime_thresholds: Optional[Dict[str, float]] = None,
        volatility_window: int = 20,
        trend_window: int = 20,
        health_window: int = 20,
        alert_thresholds: Optional[Dict[str, float]] = None,
        logger: Any = None,
    ) -> None:
        self.session_name = session_name
        self.candles = candles.copy()
        self.engine = engine
        self.signal_source = signal_source
        self.baseline_metrics = baseline_metrics or {}
        self.regime_thresholds = {**DEFAULT_REGIME_THRESHOLDS, **(regime_thresholds or {})}
        self.volatility_window = volatility_window
        self.trend_window = trend_window
        self.health_window = health_window
        self.alert_thresholds = {
            "sharpe_decay_pct": 0.25,
            "drawdown_pct": 0.15,
            "slippage_pct": 0.5,
            "stability_decay_pct": 0.25,
            **(alert_thresholds or {}),
        }
        self.logger = logger
        self.history: List[Dict[str, Any]] = []
        self.regime_map: Dict[datetime, RegimeType] = {}
        self.summary: Optional[ValidationSessionResult] = None

    def _normalize_signal_source(self) -> Dict[datetime, Any]:
        if self.signal_source is None:
            return {}
        if callable(self.signal_source):
            return {}
        if isinstance(self.signal_source, pd.Series):
            return {timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp: signal for timestamp, signal in self.signal_source.items()}
        return {timestamp: signal for timestamp, signal in self.signal_source.items()}

    def _classify_regimes(self) -> pd.Series:
        close = self.candles["close"].astype(float)
        returns = close.pct_change().fillna(0.0)
        volatility = returns.rolling(self.volatility_window, min_periods=1).std().fillna(0.0)
        trend_periods = min(self.trend_window, max(1, len(close) - 1))
        trend_strength = close.pct_change(periods=trend_periods).fillna(0.0).abs()

        labels: List[RegimeType] = []
        for vol, trend in zip(volatility, trend_strength):
            if vol >= self.regime_thresholds["high_volatility"]:
                labels.append("high_volatility")
            elif vol <= self.regime_thresholds["low_volatility"]:
                labels.append("low_volatility")
            elif trend >= self.regime_thresholds["trend_pct"]:
                labels.append("trending")
            else:
                labels.append("ranging")
        regime_series = pd.Series(labels, index=self.candles.index)
        self.regime_map = {ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts: regime for ts, regime in regime_series.items()}
        return regime_series

    def _compute_rolling_metrics(self, equity: List[float], timestamps: List[datetime]) -> pd.DataFrame:
        adjusted_equity = equity
        if len(equity) == len(timestamps) + 1:
            adjusted_equity = equity[1:]
        elif len(equity) != len(timestamps):
            adjusted_equity = equity[-len(timestamps) :]
        series = pd.Series(adjusted_equity, index=pd.to_datetime(timestamps))
        returns = series.pct_change().fillna(0.0)
        rolling_vol = returns.rolling(self.health_window, min_periods=2).std().fillna(0.0)
        rolling_mean = returns.rolling(self.health_window, min_periods=2).mean().fillna(0.0)
        rolling_sharpe = rolling_mean.div(rolling_vol.replace(0.0, np.nan)).fillna(0.0) * np.sqrt(252)
        rolling_max = series.cummax()
        drawdown = (series - rolling_max) / rolling_max.replace(0.0, np.nan)
        rolling_drawdown = drawdown.rolling(self.health_window, min_periods=1).min().fillna(0.0)
        stability = 1.0 / (1.0 + rolling_vol)

        return pd.DataFrame(
            {
                "equity": series,
                "returns": returns,
                "rolling_sharpe": rolling_sharpe,
                "rolling_volatility": rolling_vol,
                "drawdown": drawdown.fillna(0.0),
                "rolling_drawdown": rolling_drawdown,
                "stability": stability.fillna(1.0),
            }
        )

    def _compute_execution_quality(self) -> pd.DataFrame:
        execution_events = [event for event in self.engine.execution_log if event.get("order") is not None or event.get("reason") in {"entry", "signal_flip", "signal_close"}]
        if not execution_events:
            return pd.DataFrame()

        records = []
        for event in execution_events:
            records.append(
                {
                    "timestamp": pd.to_datetime(event.get("timestamp")),
                    "slippage_cost": float(event.get("slippage_cost", 0.0) or 0.0),
                    "fee_cost": float(event.get("fee_cost", 0.0) or 0.0),
                    "price": float(event.get("price", 0.0) or 0.0),
                    "pnl": float(event.get("pnl", 0.0) or 0.0),
                }
            )
        df = pd.DataFrame(records).set_index("timestamp").sort_index()
        if df.empty:
            return df
        df["slippage_pct"] = np.where(df["price"] > 0.0, df["slippage_cost"] / df["price"], 0.0)
        df["fee_pct"] = np.where(df["price"] > 0.0, df["fee_cost"] / df["price"], 0.0)
        return df

    def _compute_regime_metrics(self, regime_series: pd.Series, performance_frame: pd.DataFrame) -> Dict[str, Any]:
        regime_metrics: Dict[str, Any] = {}
        for regime in regime_series.unique():
            regime_index = regime_series[regime_series == regime].index
            if regime_index.empty:
                continue
            regime_equity = performance_frame.reindex(regime_index, method="ffill")["equity"].dropna()
            regime_returns = regime_equity.pct_change().fillna(0.0)
            regime_metrics[regime] = {
                "duration": int(len(regime_equity)),
                "net_return": float(regime_equity.iloc[-1] / regime_equity.iloc[0] - 1.0) if len(regime_equity) > 1 else 0.0,
                "sharpe": float(regime_returns.mean() / regime_returns.std() * np.sqrt(252)) if regime_returns.std() > 0 else 0.0,
                "drawdown": float((regime_equity / regime_equity.cummax() - 1.0).min()) if not regime_equity.empty else 0.0,
                "volatility": float(regime_returns.std()),
                "stability": float(1.0 / (1.0 + regime_returns.std())) if regime_returns.std() > 0 else 1.0,
            }
        return regime_metrics

    def _build_summary_panels(self, performance_frame: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if performance_frame.empty:
            return [], []

        daily = performance_frame.resample("D").last()
        weekly = performance_frame.resample("W").last()
        return (
            [
                {
                    "period": idx.strftime("%Y-%m-%d"),
                    "equity": float(row["equity"]),
                    "cumulative_return": float(row["equity"] / performance_frame.iloc[0]["equity"] - 1.0),
                    "rolling_sharpe": float(row["rolling_sharpe"]),
                    "drawdown": float(row["drawdown"]),
                    "stability": float(row["stability"]),
                }
                for idx, row in daily.iterrows()
            ],
            [
                {
                    "period": idx.strftime("%Y-%m-%d"),
                    "equity": float(row["equity"]),
                    "cumulative_return": float(row["equity"] / performance_frame.iloc[0]["equity"] - 1.0),
                    "rolling_sharpe": float(row["rolling_sharpe"]),
                    "drawdown": float(row["drawdown"]),
                    "stability": float(row["stability"]),
                }
                for idx, row in weekly.iterrows()
            ],
        )

    def _detect_degradation(self, performance_frame: pd.DataFrame, execution_quality: pd.DataFrame) -> List[str]:
        alerts: List[str] = []
        if performance_frame.empty:
            return alerts

        if len(performance_frame) >= self.health_window:
            start_sharpe = float(performance_frame.iloc[0]["rolling_sharpe"])
            end_sharpe = float(performance_frame.iloc[-1]["rolling_sharpe"])
            if start_sharpe > 0 and (start_sharpe - end_sharpe) / max(abs(start_sharpe), 1e-9) > self.alert_thresholds["sharpe_decay_pct"]:
                alerts.append("weakening_edge")

        recent_dd = float(performance_frame.iloc[-1]["drawdown"])
        if recent_dd < -self.alert_thresholds["drawdown_pct"]:
            alerts.append("rising_drawdown")

        if execution_quality.shape[0] >= 2:
            first_half = execution_quality.iloc[: max(1, len(execution_quality) // 2)]
            second_half = execution_quality.iloc[max(1, len(execution_quality) // 2) :]
            if not first_half.empty and not second_half.empty:
                first_slip = float(first_half["slippage_pct"].mean())
                second_slip = float(second_half["slippage_pct"].mean())
                if first_slip > 0 and (second_slip - first_slip) / first_slip > self.alert_thresholds["slippage_pct"]:
                    alerts.append("slippage_drift")

        stability_start = float(performance_frame.iloc[0]["stability"])
        stability_end = float(performance_frame.iloc[-1]["stability"])
        if stability_start > 0 and (stability_start - stability_end) / stability_start > self.alert_thresholds["stability_decay_pct"]:
            alerts.append("strategy_instability")

        return alerts

    def _build_drift_report(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        drift: Dict[str, Any] = {"flags": [], "changes": {}}
        if not self.baseline_metrics:
            return drift

        for key in ["sharpe", "drawdown", "net_return", "stability"]:
            baseline_value = float(self.baseline_metrics.get(key, 0.0) or 0.0)
            live_value = float(metrics.get(key, 0.0) or 0.0)
            if baseline_value != 0.0:
                change = (live_value - baseline_value) / abs(baseline_value)
                drift["changes"][key] = change
                if key == "drawdown" and change < -0.15:
                    drift["flags"].append("drawdown_drift")
                if key == "sharpe" and change < -0.2:
                    drift["flags"].append("sharpe_drift")
        return drift

    def run(
        self,
        accelerated: bool = False,
        disconnect_windows: Optional[List[Tuple[datetime, datetime]]] = None,
        volatility_spike_windows: Optional[List[Tuple[datetime, datetime]]] = None,
        slippage_spike_windows: Optional[List[Tuple[datetime, datetime]]] = None,
        slippage_multiplier: float = 1.0,
    ) -> ValidationSessionResult:
        signals = self._normalize_signal_source()
        regime_series = self._classify_regimes()
        disconnect_windows = disconnect_windows or []
        volatility_spike_windows = volatility_spike_windows or []
        slippage_spike_windows = slippage_spike_windows or []
        original_slippage = self.engine.slippage_pct
        start_timestamp = self.candles.index[0].to_pydatetime() if hasattr(self.candles.index[0], "to_pydatetime") else self.candles.index[0]

        for timestamp, row in self.candles.iterrows():
            now = timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp
            if any(start <= now <= end for start, end in disconnect_windows):
                continue

            self.engine.slippage_pct = original_slippage * slippage_multiplier if any(start <= now <= end for start, end in slippage_spike_windows) else original_slippage
            if any(start <= now <= end for start, end in volatility_spike_windows):
                volatility_factor = 1.5
                row = row.copy()
                row["high"] = float(row["close"] * (1.0 + volatility_factor * 0.01))
                row["low"] = float(row["close"] * (1.0 - volatility_factor * 0.01))

            signal = signals.get(now)
            if signal is None and callable(self.signal_source):
                signal = self.signal_source(row, self.engine)
            if signal is not None:
                self.engine.process_signal(signal, now)

            self.engine.on_market_candle(
                {
                    "timestamp": now,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0.0)),
                },
                latency_ms=0.0,
                timestamp=now,
            )
            if accelerated:
                continue

        self.engine.slippage_pct = original_slippage
        performance_frame = self._compute_rolling_metrics(self.engine.equity_curve, self.engine.equity_timestamps)
        execution_quality = self._compute_execution_quality()
        regime_metrics = self._compute_regime_metrics(regime_series, performance_frame)
        daily_summary, weekly_summary = self._build_summary_panels(performance_frame)
        alerts = self._detect_degradation(performance_frame, execution_quality)
        metrics = {
            "net_return": float(performance_frame.iloc[-1]["equity"] / performance_frame.iloc[0]["equity"] - 1.0) if not performance_frame.empty else 0.0,
            "sharpe": float(performance_frame.iloc[-1]["rolling_sharpe"] if not performance_frame.empty else 0.0),
            "drawdown": float(performance_frame.iloc[-1]["drawdown"] if not performance_frame.empty else 0.0),
            "volatility": float(performance_frame.iloc[-1]["rolling_volatility"] if not performance_frame.empty else 0.0),
            "stability": float(performance_frame.iloc[-1]["stability"] if not performance_frame.empty else 1.0),
            "executions": int(len(execution_quality)),
            "average_slippage_pct": float(execution_quality["slippage_pct"].mean() if not execution_quality.empty else 0.0),
        }
        drift_report = self._build_drift_report(metrics)
        self.summary = ValidationSessionResult(
            session_name=self.session_name,
            start_time=start_timestamp,
            end_time=self.candles.index[-1].to_pydatetime() if hasattr(self.candles.index[-1], "to_pydatetime") else self.candles.index[-1],
            metrics=metrics,
            regime_metrics=regime_metrics,
            daily_summary=daily_summary,
            weekly_summary=weekly_summary,
            alerts=alerts,
            drift_report=drift_report,
            health_history=[
                {
                    "timestamp": idx.strftime("%Y-%m-%dT%H:%M:%S"),
                    "rolling_sharpe": float(row["rolling_sharpe"]),
                    "drawdown": float(row["drawdown"]),
                    "stability": float(row["stability"]),
                }
                for idx, row in performance_frame.iterrows()
            ],
            execution_quality_history=[
                {
                    "timestamp": idx.strftime("%Y-%m-%dT%H:%M:%S"),
                    "slippage_pct": float(row["slippage_pct"]),
                    "fee_pct": float(row["fee_pct"]),
                    "pnl": float(row["pnl"]),
                }
                for idx, row in execution_quality.iterrows()
            ],
            regime_map=self.regime_map,
            equity_curve=self.engine.equity_curve.copy(),
            equity_timestamps=[ts.isoformat() for ts in self.engine.equity_timestamps],
        )
        return self.summary


class MultiSessionForwardTester:
    def __init__(self, logger: Any = None) -> None:
        self.logger = logger
        self.session_results: List[ValidationSessionResult] = []
        self.alerts: List[str] = []

    def run_sessions(
        self,
        sessions: List[Dict[str, Any]],
        accelerated: bool = False,
    ) -> Dict[str, Any]:
        self.session_results = []
        self.alerts = []
        for session_config in sessions:
            try:
                session = LiveValidationSession(
                    session_name=session_config.get("name", f"session_{len(self.session_results) + 1}"),
                    candles=session_config["candles"],
                    engine=session_config["engine"],
                    signal_source=session_config.get("signal_source"),
                    baseline_metrics=session_config.get("baseline_metrics"),
                    regime_thresholds=session_config.get("regime_thresholds"),
                    volatility_window=session_config.get("volatility_window", 20),
                    trend_window=session_config.get("trend_window", 20),
                    health_window=session_config.get("health_window", 20),
                    alert_thresholds=session_config.get("alert_thresholds"),
                    logger=self.logger,
                )
                result = session.run(
                    accelerated=accelerated,
                    disconnect_windows=session_config.get("disconnect_windows"),
                    volatility_spike_windows=session_config.get("volatility_spike_windows"),
                    slippage_spike_windows=session_config.get("slippage_spike_windows"),
                    slippage_multiplier=session_config.get("slippage_multiplier", 1.0),
                )
                self.session_results.append(result)
                self.alerts.extend(result.alerts)
            except Exception:
                if self.logger:
                    self.logger.exception("Forward validation session failed: %s", session_config.get("name"))
        return self.generate_report()

    def generate_report(self) -> Dict[str, Any]:
        combined_metrics = {
            "session_count": len(self.session_results),
            "overall_alerts": self.alerts,
            "session_summaries": [result.__dict__ for result in self.session_results],
        }
        if self.session_results:
            combined_metrics["aggregate_drawdown"] = min(result.metrics.get("drawdown", 0.0) for result in self.session_results)
            combined_metrics["aggregate_sharpe"] = float(np.mean([result.metrics.get("sharpe", 0.0) for result in self.session_results]))
            combined_metrics["sessions_with_alerts"] = len([result for result in self.session_results if result.alerts])
        return combined_metrics
