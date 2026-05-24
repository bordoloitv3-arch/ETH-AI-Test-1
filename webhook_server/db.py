import sqlite3
import threading
from typing import Any, Dict, Optional

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY, hash TEXT UNIQUE, symbol TEXT, timeframe TEXT, signal TEXT, strategy TEXT, params TEXT, timestamp TEXT, price REAL, received_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS executions (id INTEGER PRIMARY KEY, alert_hash TEXT, order_id INTEGER, status TEXT, price REAL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS positions (id INTEGER PRIMARY KEY, entry_order_id INTEGER, exit_order_id INTEGER, entry_price REAL, exit_price REAL, size REAL, opened_at DATETIME, closed_at DATETIME)",
    "CREATE TABLE IF NOT EXISTS errors (id INTEGER PRIMARY KEY, alert_hash TEXT, message TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS metrics (id INTEGER PRIMARY KEY, key TEXT, value REAL, tags TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
]

_lock = threading.Lock()


def get_conn(path: str = "webhook_state.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str = "webhook_state.db") -> None:
    conn = get_conn(path)
    cur = conn.cursor()
    for s in SCHEMA:
        cur.execute(s)
    conn.commit()
    conn.close()


def insert_alert(hash_hex: str, payload: Dict[str, Any], path: str = "webhook_state.db") -> bool:
    conn = get_conn(path)
    cur = conn.cursor()
    try:
        with _lock:
            cur.execute(
                "INSERT INTO alerts (hash, symbol, timeframe, signal, strategy, params, timestamp, price) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    hash_hex,
                    payload.get("symbol"),
                    payload.get("timeframe"),
                    payload.get("signal"),
                    payload.get("strategy"),
                    str(payload.get("params")),
                    str(payload.get("timestamp")),
                    payload.get("price"),
                ),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def record_execution(alert_hash: str, order_id: int, status: str, price: Optional[float] = None, path: str = "webhook_state.db") -> None:
    conn = get_conn(path)
    cur = conn.cursor()
    with _lock:
        cur.execute(
            "INSERT INTO executions (alert_hash, order_id, status, price) VALUES (?, ?, ?, ?)", (alert_hash, order_id, status, price)
        )
        conn.commit()
    conn.close()


def record_error(alert_hash: Optional[str], message: str, path: str = "webhook_state.db") -> None:
    conn = get_conn(path)
    cur = conn.cursor()
    with _lock:
        cur.execute("INSERT INTO errors (alert_hash, message) VALUES (?, ?)", (alert_hash, message))
        conn.commit()
    conn.close()


def write_metric(key: str, value: float, tags: Optional[str] = None, path: str = "webhook_state.db") -> None:
    conn = get_conn(path)
    cur = conn.cursor()
    with _lock:
        cur.execute("INSERT INTO metrics (key, value, tags) VALUES (?, ?, ?)", (key, value, tags))
        conn.commit()
    conn.close()
