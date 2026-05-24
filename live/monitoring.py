from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


class LiveStateStore:
    def __init__(self, directory: str = "memory/live_state", logger: Any = None) -> None:
        self.base_dir = Path(directory)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger
        self.snapshot_path = self.base_dir / "live_snapshot.json"
        self.backup_path = self.base_dir / "live_snapshot.bak.json"
        self.metrics_path = self.base_dir / "live_metrics.json"
        self.health_path = self.base_dir / "live_health.json"

    def _safe_write(self, path: Path, payload: Dict[str, Any]) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, default=self._json_default, indent=2)
        if path.exists():
            path.replace(self.backup_path)
        temp_path.replace(path)
        if self.logger:
            self.logger.info("Persisted live state to %s", path)

    def _json_default(self, obj: Any) -> str:
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)

    def save_snapshot(self, payload: Dict[str, Any]) -> Path:
        self._safe_write(self.snapshot_path, payload)
        return self.snapshot_path

    def save_metrics(self, payload: Dict[str, Any]) -> Path:
        self._safe_write(self.metrics_path, payload)
        return self.metrics_path

    def save_health(self, payload: Dict[str, Any]) -> Path:
        self._safe_write(self.health_path, payload)
        return self.health_path

    def load_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        for path in (self.snapshot_path, self.backup_path):
            if path.exists():
                try:
                    with path.open("r", encoding="utf-8") as handle:
                        return json.load(handle)
                except Exception:
                    if self.logger:
                        self.logger.exception("Failed to load live snapshot from %s", path)
        return None

    def clean_old_snapshots(self, keep: int = 3) -> None:
        snapshots = sorted(self.base_dir.glob("live_snapshot*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old_snapshot in snapshots[keep:]:
            try:
                old_snapshot.unlink()
            except Exception:
                if self.logger:
                    self.logger.exception("Failed to remove old snapshot %s", old_snapshot)


class LiveMetricsCollector:
    def __init__(self, logger: Any = None, enable_prometheus: bool = False, prometheus_port: int = 8000) -> None:
        self.logger = logger
        self.event_counts: Dict[str, int] = {
            "kline": 0,
            "trade": 0,
            "depth": 0,
            "reconnect": 0,
            "watchdog_timeout": 0,
            "errors": 0,
        }
        self.latencies: List[float] = []
        self.orders: int = 0
        self.executions: int = 0
        self.signals: int = 0
        self.last_snapshot_at: Optional[datetime] = None
        self.system_metrics: Dict[str, Any] = {}
        self.prometheus_registry = None
        self.prometheus_enabled = enable_prometheus
        self.prometheus_port = prometheus_port

        if enable_prometheus:
            self._init_prometheus()

    def _init_prometheus(self) -> None:
        try:
            from prometheus_client import Gauge, start_http_server
        except ImportError:  # pragma: no cover
            self.prometheus_enabled = False
            if self.logger:
                self.logger.warning("prometheus_client is not installed; Prometheus metrics are disabled.")
            return

        try:
            start_http_server(self.prometheus_port)
            self.prometheus_registry = {
                "live_latency_ms": Gauge("live_latency_ms", "Live stream latency in milliseconds"),
                "live_executions": Gauge("live_executions", "Live execution count"),
                "live_orders": Gauge("live_orders", "Live order count"),
                "live_signals": Gauge("live_signals", "Live signal count"),
                "live_reconnects": Gauge("live_reconnects", "Live stream reconnect count"),
                "live_health_score": Gauge("live_health_score", "Live system health score"),
            }
            if self.logger:
                self.logger.info("Prometheus exporter bound to port %d", self.prometheus_port)
        except Exception:
            self.prometheus_enabled = False
            if self.logger:
                self.logger.exception("Failed to start Prometheus exporter.")

    def record_event(self, event: str) -> None:
        self.event_counts[event] = self.event_counts.get(event, 0) + 1

    def record_latency(self, latency_ms: Optional[float]) -> None:
        if latency_ms is None:
            return
        self.latencies.append(float(latency_ms))

    def record_order(self) -> None:
        self.orders += 1

    def record_execution(self) -> None:
        self.executions += 1

    def record_signal(self) -> None:
        self.signals += 1

    def collect_system_metrics(self) -> Dict[str, Any]:
        metrics: Dict[str, Any] = {}
        if psutil is None:
            return metrics
        process = psutil.Process()
        try:
            metrics = {
                "cpu_percent": process.cpu_percent(interval=0.1),
                "memory_rss_bytes": process.memory_info().rss,
                "memory_vms_bytes": process.memory_info().vms,
                "thread_count": process.num_threads(),
                "uptime_seconds": max(0.0, datetime.now(timezone.utc).timestamp() - process.create_time()),
            }
        except Exception:
            if self.logger:
                self.logger.exception("Failed to collect system metrics.")
        self.system_metrics = metrics
        return metrics

    def export_summary(self) -> Dict[str, Any]:
        latency_summary: Dict[str, Any] = {
            "count": len(self.latencies),
            "average_ms": float(sum(self.latencies) / len(self.latencies)) if self.latencies else 0.0,
            "max_ms": float(max(self.latencies)) if self.latencies else 0.0,
            "min_ms": float(min(self.latencies)) if self.latencies else 0.0,
        }
        metrics = {
            "event_counts": dict(self.event_counts),
            "latency": latency_summary,
            "orders": self.orders,
            "executions": self.executions,
            "signals": self.signals,
            "system_metrics": self.collect_system_metrics(),
            "last_snapshot_at": self.last_snapshot_at.isoformat() if self.last_snapshot_at else None,
        }
        if self.prometheus_enabled and self.prometheus_registry is not None:
            self._export_prometheus(metrics)
        return metrics

    def mark_snapshot(self) -> None:
        self.last_snapshot_at = datetime.now(timezone.utc)

    def _export_prometheus(self, metrics: Dict[str, Any]) -> None:
        try:
            self.prometheus_registry["live_latency_ms"].set(metrics["latency"]["average_ms"])
            self.prometheus_registry["live_executions"].set(metrics["executions"])
            self.prometheus_registry["live_orders"].set(metrics["orders"])
            self.prometheus_registry["live_signals"].set(metrics["signals"])
            self.prometheus_registry["live_reconnects"].set(metrics["event_counts"].get("reconnect", 0))
            self.prometheus_registry["live_health_score"].set(metrics.get("system_metrics", {}).get("cpu_percent", 0.0))
        except Exception:
            if self.logger:
                self.logger.exception("Failed to export Prometheus metrics.")


class LiveHealthScorer:
    def __init__(
        self,
        latency_threshold_ms: float = 500.0,
        drawdown_threshold: float = 0.15,
        reconnect_threshold: int = 3,
        logger: Any = None,
    ) -> None:
        self.latency_threshold_ms = float(latency_threshold_ms)
        self.drawdown_threshold = float(drawdown_threshold)
        self.reconnect_threshold = int(reconnect_threshold)
        self.logger = logger

    def compute_score(self, state: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
        latency = metrics.get("latency", {}).get("average_ms", 0.0)
        drawdown = abs(state.get("drawdown", 0.0))
        reconnects = metrics.get("event_counts", {}).get("reconnect", 0)
        emergency_stopped = bool(state.get("emergency_stopped", False))

        latency_score = max(0.0, 1.0 - min(latency / self.latency_threshold_ms, 1.0))
        drawdown_score = max(0.0, 1.0 - min(drawdown / self.drawdown_threshold, 1.0))
        reconnect_score = max(0.0, 1.0 - min(reconnects / self.reconnect_threshold, 1.0))
        stability_score = float(metrics.get("orders", 0) + 1) / max(float(metrics.get("executions", 0) + 1), 1.0)

        base_score = 0.4 * latency_score + 0.3 * drawdown_score + 0.2 * reconnect_score + 0.1 * min(stability_score, 1.0)
        if emergency_stopped:
            base_score *= 0.5

        health_summary = {
            "health_score": round(base_score * 100.0, 2),
            "latency_score": round(latency_score * 100.0, 2),
            "drawdown_score": round(drawdown_score * 100.0, 2),
            "reconnect_score": round(reconnect_score * 100.0, 2),
            "stability_score": round(min(stability_score, 1.0) * 100.0, 2),
            "emergency_stopped": emergency_stopped,
        }
        return health_summary


class LiveDriftDetector:
    def __init__(self, baseline_metrics: Optional[Dict[str, Any]] = None, thresholds: Optional[Dict[str, float]] = None) -> None:
        self.baseline_metrics = baseline_metrics or {}
        self.thresholds = thresholds or {
            "latency_pct": 0.5,
            "drawdown_pct": 0.33,
            "execution_pct": 0.5,
        }

    def update_baseline(self, baseline_metrics: Dict[str, Any]) -> None:
        self.baseline_metrics = baseline_metrics.copy()

    def evaluate(self, state: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
        report: Dict[str, Any] = {"drift_flags": [], "drift_percentages": {}}
        baseline_latency = float(self.baseline_metrics.get("latency", {}).get("average_ms", 0.0))
        current_latency = float(metrics.get("latency", {}).get("average_ms", 0.0))
        if baseline_latency > 0:
            latency_change = (current_latency - baseline_latency) / baseline_latency
            report["drift_percentages"]["latency"] = latency_change
            if latency_change > self.thresholds["latency_pct"]:
                report["drift_flags"].append("latency")

        baseline_drawdown = abs(float(self.baseline_metrics.get("drawdown", 0.0)))
        current_drawdown = abs(float(state.get("drawdown", 0.0)))
        if baseline_drawdown > 0:
            drawdown_change = (current_drawdown - baseline_drawdown) / baseline_drawdown
            report["drift_percentages"]["drawdown"] = drawdown_change
            if drawdown_change > self.thresholds["drawdown_pct"]:
                report["drift_flags"].append("drawdown")

        baseline_executions = float(self.baseline_metrics.get("executions", 0.0))
        current_executions = float(metrics.get("executions", 0.0))
        if baseline_executions > 0:
            execution_change = (current_executions - baseline_executions) / baseline_executions
            report["drift_percentages"]["executions"] = execution_change
            if abs(execution_change) > self.thresholds["execution_pct"]:
                report["drift_flags"].append("execution_volume")

        return report
