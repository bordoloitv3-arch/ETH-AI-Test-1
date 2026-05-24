from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

try:
    import websocket
except ImportError:  # pragma: no cover
    websocket = None


EventCallback = Callable[[Dict[str, Any]], None]


class BinanceFuturesMarketStream:
    BASE_URL = "wss://fstream.binance.com/stream?streams="
    DEFAULT_DEPTH_SPEED = "100ms"
    DEFAULT_RECONNECT_DELAY = 5.0
    DEFAULT_WATCHDOG_INTERVAL = 15.0
    DEFAULT_WATCHDOG_TIMEOUT = 20.0

    def __init__(
        self,
        symbol: str = "ETHUSDT",
        interval: str = "1m",
        depth_speed: str = DEFAULT_DEPTH_SPEED,
        logger: Any = None,
        reconnect_delay: float = DEFAULT_RECONNECT_DELAY,
        watchdog_interval: float = DEFAULT_WATCHDOG_INTERVAL,
        watchdog_timeout: float = DEFAULT_WATCHDOG_TIMEOUT,
    ) -> None:
        self.symbol = symbol.upper()
        self.interval = interval
        self.depth_speed = depth_speed
        self.logger = logger
        self.reconnect_delay = reconnect_delay
        self.watchdog_interval = watchdog_interval
        self.watchdog_timeout = watchdog_timeout
        self._callbacks: Dict[str, List[EventCallback]] = defaultdict(list)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self._ws: Optional[Any] = None
        self.last_message_at = datetime.now(timezone.utc)
        self.latency_ms: Optional[float] = None
        self.reconnect_count = 0
        self.connection_status = "disconnected"

    @property
    def url(self) -> str:
        streams = [
            f"{self.symbol.lower()}@kline_{self.interval}",
            f"{self.symbol.lower()}@trade",
            f"{self.symbol.lower()}@depth5@{self.depth_speed}",
        ]
        return self.BASE_URL + "/".join(streams)

    def register_callback(self, event: str, callback: EventCallback) -> None:
        self._callbacks[event].append(callback)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=2.0)
        self.connection_status = "disconnected"

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._connect()
            except Exception as exc:
                self.connection_status = "error"
                self._emit("error", {"error": str(exc)})
                if self.logger:
                    self.logger.warning("Binance stream failed: %s", exc)
            if self._stop_event.is_set():
                break
            self.reconnect_count += 1
            self.connection_status = "reconnecting"
            self._emit("reconnect", {"count": self.reconnect_count})
            time.sleep(self.reconnect_delay)

    def _connect(self) -> None:
        if websocket is None:
            raise ImportError(
                "websocket-client is required for Binance live streams. Install with `pip install websocket-client`."
            )
        self.connection_status = "connecting"
        self._emit("connecting", {})
        self._ws = websocket.WebSocketApp(
            self.url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._ws.run_forever(ping_interval=20, ping_timeout=10, ping_payload="keepalive")

    def _on_open(self, ws: Any) -> None:
        self.connection_status = "connected"
        self.last_message_at = datetime.now(timezone.utc)
        self._emit("connected", {"url": self.url})
        if self.logger:
            self.logger.info("Binance stream connected: %s", self.url)

    def _on_message(self, ws: Any, message: str) -> None:
        self.last_message_at = datetime.now(timezone.utc)
        payload = json.loads(message)
        stream = payload.get("stream", "")
        data = payload.get("data", {})
        event: Dict[str, Any] = {"stream": stream, "data": data, "received_at": self.last_message_at}
        self.latency_ms = self._extract_latency(data)
        event["latency_ms"] = self.latency_ms
        if stream.endswith("@kline_" + self.interval):
            self._emit("kline", self._normalize_kline(data, event["received_at"]))
        elif stream.endswith("@trade"):
            self._emit("trade", self._normalize_trade(data, event["received_at"]))
        elif "depth" in stream:
            self._emit("depth", self._normalize_depth(data, event["received_at"]))
        else:
            self._emit("message", event)

    def _on_error(self, ws: Any, error: Any) -> None:
        self.connection_status = "error"
        self._emit("error", {"error": str(error)})
        if self.logger:
            self.logger.warning("Binance stream error: %s", error)

    def _on_close(self, ws: Any, close_status_code: int, close_msg: str) -> None:
        self.connection_status = "disconnected"
        self._emit("disconnected", {"code": close_status_code, "reason": close_msg})
        if self.logger:
            self.logger.info("Binance stream disconnected: %s (%s)", close_status_code, close_msg)

    def _watchdog_loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(self.watchdog_interval)
            if self._stop_event.is_set():
                break
            age = (datetime.now(timezone.utc) - self.last_message_at).total_seconds()
            if age > self.watchdog_timeout:
                self._emit("watchdog_timeout", {"age_seconds": age})
                if self.logger:
                    self.logger.warning("Watchdog triggered reconnect after %.1f seconds", age)
                self._trigger_reconnect()

    def _trigger_reconnect(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
        self.connection_status = "reconnecting"
        self._emit("reconnect_requested", {"timestamp": datetime.now(timezone.utc)})

    def _extract_latency(self, data: Dict[str, Any]) -> Optional[float]:
        event_time = data.get("E") or data.get("T") or data.get("u")
        if event_time is None:
            return None
        event_ts = datetime.fromtimestamp(int(event_time) / 1000.0, tz=timezone.utc)
        return (datetime.now(timezone.utc) - event_ts).total_seconds() * 1000.0

    def _emit(self, event: str, payload: Dict[str, Any]) -> None:
        for callback in self._callbacks.get(event, []):
            try:
                callback(payload)
            except Exception:
                if self.logger:
                    self.logger.exception("Error running callback for %s", event)

    @staticmethod
    def _normalize_kline(data: Dict[str, Any], received_at: datetime) -> Dict[str, Any]:
        k = data.get("k", {})
        return {
            "symbol": data.get("s"),
            "interval": k.get("i"),
            "start_time": datetime.fromtimestamp(int(k.get("t", 0)) / 1000.0, tz=timezone.utc),
            "end_time": datetime.fromtimestamp(int(k.get("T", 0)) / 1000.0, tz=timezone.utc),
            "open": float(k.get("o", 0.0)),
            "high": float(k.get("h", 0.0)),
            "low": float(k.get("l", 0.0)),
            "close": float(k.get("c", 0.0)),
            "volume": float(k.get("v", 0.0)),
            "is_closed": bool(k.get("x", False)),
            "received_at": received_at,
        }

    @staticmethod
    def _normalize_trade(data: Dict[str, Any], received_at: datetime) -> Dict[str, Any]:
        return {
            "symbol": data.get("s"),
            "trade_id": int(data.get("t", 0)),
            "price": float(data.get("p", 0.0)),
            "quantity": float(data.get("q", 0.0)),
            "buyer_is_maker": bool(data.get("m", False)),
            "trade_time": datetime.fromtimestamp(int(data.get("T", 0)) / 1000.0, tz=timezone.utc),
            "received_at": received_at,
        }

    @staticmethod
    def _normalize_depth(data: Dict[str, Any], received_at: datetime) -> Dict[str, Any]:
        return {
            "symbol": data.get("s"),
            "last_update_id": int(data.get("u", 0)),
            "first_update_id": int(data.get("U", 0)),
            "bids": data.get("b", []),
            "asks": data.get("a", []),
            "received_at": received_at,
        }
