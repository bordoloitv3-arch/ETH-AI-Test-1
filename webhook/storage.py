from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional


class WebhookStorage:
    def __init__(
        self,
        db_path: str = "memory/webhook/webhook.db",
        alert_csv: str = "logs/webhook/alerts.csv",
        error_csv: str = "logs/webhook/errors.csv",
        report_dir: str = "reports/webhook",
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.alert_csv = Path(alert_csv)
        self.error_csv = Path(error_csv)
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._initialize_schema()
        self._ensure_csv(self.alert_csv, ["alert_id", "received_at", "symbol", "timeframe", "signal", "strategy_name", "timestamp", "price", "alert_hash"])
        self._ensure_csv(self.error_csv, ["error_id", "created_at", "context", "message"])

    def _initialize_schema(self) -> None:
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    received_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    price REAL NOT NULL,
                    strategy_parameters TEXT,
                    risk_settings TEXT,
                    metadata TEXT,
                    alert_hash TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id INTEGER,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT,
                    FOREIGN KEY(alert_id) REFERENCES alerts(alert_id)
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    position_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    position_snapshot TEXT NOT NULL
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS errors (
                    error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    message TEXT NOT NULL,
                    context TEXT
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics (
                    metrics_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    metrics_snapshot TEXT NOT NULL
                )
                """
            )

    def _ensure_csv(self, path: Path, headers: List[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()

    def _serialize(self, payload: Any) -> str:
        return json.dumps(payload, default=str)

    def _now(self) -> str:
        return datetime.utcnow().isoformat() + "Z"

    def compute_hash(self, payload: Dict[str, Any]) -> str:
        payload_text = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(payload_text.encode("utf-8")).hexdigest()

    def insert_alert(self, payload: Dict[str, Any], alert_hash: str) -> int:
        with self._lock, self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO alerts
                    (received_at, symbol, timeframe, signal, strategy_name, timestamp, price, strategy_parameters, risk_settings, metadata, alert_hash, payload)
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._now(),
                    payload["symbol"],
                    payload["timeframe"],
                    payload["signal"],
                    payload["strategy_name"],
                    payload["timestamp"],
                    payload["price"],
                    self._serialize(payload.get("strategy_parameters", {})),
                    self._serialize(payload.get("risk_settings", {})),
                    self._serialize(payload.get("metadata", {})),
                    alert_hash,
                    self._serialize(payload),
                ),
            )
            alert_id = int(cursor.lastrowid)
            self._append_csv(self.alert_csv, {
                "alert_id": alert_id,
                "received_at": self._now(),
                "symbol": payload["symbol"],
                "timeframe": payload["timeframe"],
                "signal": payload["signal"],
                "strategy_name": payload["strategy_name"],
                "timestamp": payload["timestamp"],
                "price": payload["price"],
                "alert_hash": alert_hash,
            })
            return alert_id

    def insert_execution(self, alert_id: int, event_type: str, details: Dict[str, Any]) -> int:
        with self._lock, self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO executions (alert_id, created_at, event_type, details)
                VALUES (?, ?, ?, ?)
                """,
                (alert_id, self._now(), event_type, self._serialize(details)),
            )
            return int(cursor.lastrowid)

    def insert_position_snapshot(self, snapshot: Dict[str, Any]) -> int:
        with self._lock, self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO positions (created_at, position_snapshot)
                VALUES (?, ?)
                """,
                (self._now(), self._serialize(snapshot)),
            )
            return int(cursor.lastrowid)

    def insert_error(self, message: str, context: Optional[Dict[str, Any]] = None) -> int:
        with self._lock, self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO errors (created_at, message, context)
                VALUES (?, ?, ?)
                """,
                (self._now(), message, self._serialize(context or {})),
            )
            self._append_csv(self.error_csv, {
                "error_id": cursor.lastrowid,
                "created_at": self._now(),
                "context": self._serialize(context or {}),
                "message": message,
            })
            return int(cursor.lastrowid)

    def insert_metrics(self, metrics: Dict[str, Any]) -> int:
        with self._lock, self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO metrics (created_at, metrics_snapshot)
                VALUES (?, ?)
                """,
                (self._now(), self._serialize(metrics)),
            )
            return int(cursor.lastrowid)

    def is_duplicate_alert(self, alert_hash: str) -> bool:
        cursor = self.conn.execute("SELECT 1 FROM alerts WHERE alert_hash = ?", (alert_hash,))
        return cursor.fetchone() is not None

    def get_latest_alert(self) -> Optional[Dict[str, Any]]:
        cursor = self.conn.execute("SELECT * FROM alerts ORDER BY alert_id DESC LIMIT 1")
        row = cursor.fetchone()
        return dict(row) if row else None

    def _append_csv(self, path: Path, row: Dict[str, Any]) -> None:
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=row.keys())
            writer.writerow(row)

    def dump_json_report(self, name: str, payload: Dict[str, Any]) -> Path:
        path = self.report_dir / f"{name}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, default=str, indent=2)
        return path
