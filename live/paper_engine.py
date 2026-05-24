from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import numpy as np

from utils.timestamp_utils import normalize_timestamp_to_date
from utils.types import TradeRecord


@dataclass
class LiveOrder:
    id: int
    side: int
    size: float
    order_type: str
    limit_price: Optional[float]
    stop_price: Optional[float]
    created_at: datetime
    status: str = "open"
    filled_price: Optional[float] = None
    filled_size: float = 0.0
    slip_cost: float = 0.0
    fee_cost: float = 0.0
    message: Optional[str] = None
    size_override: Optional[float] = None
    requested_size: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        return payload


@dataclass
class LivePosition:
    direction: int
    size: float
    entry_price: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    breakeven_price: Optional[float]
    funding_accum: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["entry_time"] = self.entry_time.isoformat()
        return payload


class PaperTradingEngine:
    def __init__(
        self,
        initial_balance: float = 100000.0,
        leverage: float = 10.0,
        taker_fee: float = 0.00075,
        maker_fee: float = 0.00025,
        slippage_pct: float = 0.0005,
        spread_pct: float = 0.0,
        stop_loss_pct: float = 0.02,
        take_profit_pct: float = 0.04,
        breakeven_trigger_pct: float = 0.01,
        breakeven_buffer_pct: float = 0.0005,
        risk_pct: float = 0.01,
        size_mode: str = "risk_pct",
        max_daily_loss_pct: Optional[float] = None,
        max_drawdown_pct: Optional[float] = None,
        emergency_stop_on_violation: bool = True,
        strategy_parameters: Optional[Dict[str, Any]] = None,
        pine_config: Optional[Dict[str, Any]] = None,
        risk_management: Optional[Dict[str, Any]] = None,
        logger: Any = None,
    ) -> None:
        self.initial_balance = float(initial_balance)
        self.balance = float(initial_balance)
        self.leverage = float(leverage)
        self.taker_fee = float(taker_fee)
        self.maker_fee = float(maker_fee)
        self.slippage_pct = float(slippage_pct)
        self.spread_pct = float(spread_pct)
        self.stop_loss_pct = float(stop_loss_pct)
        self.take_profit_pct = float(take_profit_pct)
        self.breakeven_trigger_pct = float(breakeven_trigger_pct)
        self.breakeven_buffer_pct = float(breakeven_buffer_pct)
        self.risk_pct = float(risk_pct)
        self.size_mode = str(size_mode)
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.emergency_stop_on_violation = emergency_stop_on_violation
        self.strategy_parameters = strategy_parameters or {}
        self.pine_config = pine_config or {}
        self.risk_management = risk_management or {}
        self.logger = logger

        self.position: Optional[LivePosition] = None
        self.open_orders: List[LiveOrder] = []
        self.order_counter = 0
        self.equity_curve: List[float] = [self.balance]
        self.equity_timestamps: List[datetime] = []
        self.execution_log: List[Dict[str, Any]] = []
        self.order_log: List[Dict[str, Any]] = []
        self.signal_log: List[Dict[str, Any]] = []
        self.last_price: Optional[float] = None
        self.peak_equity = self.balance
        self.open_drawdown = 0.0
        self.daily_reference = self.balance
        self.current_day: Optional[datetime] = None
        self.emergency_stopped = False
        self.latency_history: List[float] = []

        self._bind_strategy_parameters()

    def _bind_strategy_parameters(self) -> None:
        if self.strategy_parameters:
            if self.strategy_parameters.get("risk_pct") is not None:
                self.risk_pct = float(self.strategy_parameters.get("risk_pct"))
            if self.strategy_parameters.get("stop_loss_pct") is not None:
                self.stop_loss_pct = float(self.strategy_parameters.get("stop_loss_pct"))
            if self.strategy_parameters.get("take_profit_pct") is not None:
                self.take_profit_pct = float(self.strategy_parameters.get("take_profit_pct"))
            if self.strategy_parameters.get("max_drawdown_pct") is not None:
                self.max_drawdown_pct = float(self.strategy_parameters.get("max_drawdown_pct"))
            if self.strategy_parameters.get("max_daily_loss_pct") is not None:
                self.max_daily_loss_pct = float(self.strategy_parameters.get("max_daily_loss_pct"))

    def _normalize_signal(self, signal: Any) -> Dict[str, Any]:
        if isinstance(signal, dict):
            return {
                "side": int(np.sign(signal.get("side", signal.get("signal", 0)))),
                "order_type": signal.get("order_type", "market"),
                "limit_price": signal.get("limit_price"),
                "stop_price": signal.get("stop_price"),
                "size_override": signal.get("size_override"),
                "breakeven_trigger_pct": float(signal.get("breakeven_trigger_pct", self.breakeven_trigger_pct)),
                "breakeven_buffer_pct": float(signal.get("breakeven_buffer_pct", self.breakeven_buffer_pct)),
            }
        return {
            "side": int(np.sign(signal)),
            "order_type": "market",
            "limit_price": None,
            "stop_price": None,
            "size_override": None,
            "breakeven_trigger_pct": self.breakeven_trigger_pct,
            "breakeven_buffer_pct": self.breakeven_buffer_pct,
        }

    def _normalize_candle(self, candle: Union[Dict[str, Any], Any], timestamp: Optional[datetime]) -> Dict[str, Any]:
        if isinstance(candle, dict):
            return {
                "timestamp": timestamp or candle.get("start_time") or candle.get("timestamp") or datetime.now(timezone.utc),
                "open": float(candle.get("open", candle.get("o", 0.0))),
                "high": float(candle.get("high", candle.get("h", 0.0))),
                "low": float(candle.get("low", candle.get("l", 0.0))),
                "close": float(candle.get("close", candle.get("c", 0.0))),
                "volume": float(candle.get("volume", candle.get("v", 0.0))),
            }
        return {
            "timestamp": timestamp or getattr(candle, "name", datetime.now(timezone.utc)),
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
            "volume": float(candle.get("volume", 0.0)),
        }

    def _calculate_order_size(self, price: float, size_override: Optional[float] = None) -> float:
        if size_override is not None and size_override > 0:
            return float(size_override)
        if price <= 0:
            return 0.0
        if self.size_mode == "risk_pct":
            risk_amount = max(self.balance * self.risk_pct, 0.0)
            risk_per_unit = max(price * self.stop_loss_pct, 1e-9)
            size = risk_amount / risk_per_unit
        elif self.size_mode == "fixed":
            size = float(self.strategy_parameters.get("fixed_size", self.balance * self.leverage / max(price, 1e-9)))
        else:
            size = self.balance * self.leverage / max(price, 1e-9)
        if self.strategy_parameters.get("max_position_size") is not None:
            size = min(size, float(self.strategy_parameters.get("max_position_size")))
        if self.risk_management.get("max_exposure_pct") is not None:
            exposure_limit = float(self.risk_management["max_exposure_pct"]) * self.balance
            size = min(size, exposure_limit / max(price, 1e-9))
        return float(max(size, 0.0))

    def _calc_fee(self, price: float, size: float, order_type: str) -> float:
        fee_rate = self.maker_fee if order_type == "limit" else self.taker_fee
        return abs(price * size) * float(fee_rate)

    def _calc_slippage(self, price: float, size: float) -> float:
        return abs(price * size) * float(self.slippage_pct)

    def _apply_breakeven(self) -> None:
        if self.position is None:
            return
        direction = self.position.direction
        current_price = self.last_price
        if current_price is None:
            return
        unrealized = direction * (current_price - self.position.entry_price) * self.position.size
        if unrealized <= 0:
            return
        trigger = abs(self.position.entry_price * self.position.size) * self.breakeven_trigger_pct
        if unrealized >= trigger:
            if direction > 0:
                self.position.stop_loss = max(self.position.stop_loss, self.position.entry_price + self.breakeven_buffer_pct)
            else:
                self.position.stop_loss = min(self.position.stop_loss, self.position.entry_price - self.breakeven_buffer_pct)

    def process_signal(self, signal: Any, timestamp: Optional[datetime] = None) -> Optional[LiveOrder]:
        if self.emergency_stopped:
            return None
        normalized = self._normalize_signal(signal)
        order_side = normalized["side"]
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        self.signal_log.append({"timestamp": timestamp.isoformat(), "signal": signal, "normalized": normalized})

        if order_side == 0:
            if self.position is not None:
                self._close_position(self.last_price or 0.0, timestamp, "signal_close")
            return None

        if self.position is not None and order_side == self.position.direction:
            return None

        requested_size = self._calculate_order_size(self.last_price or 0.0, normalized["size_override"])
        self.order_counter += 1
        order = LiveOrder(
            id=self.order_counter,
            side=order_side,
            size=requested_size,
            order_type=normalized["order_type"],
            limit_price=normalized["limit_price"],
            stop_price=normalized["stop_price"],
            created_at=timestamp,
            size_override=normalized["size_override"],
            requested_size=requested_size,
        )
        if order.size <= 0 and order.size_override is None:
            order.message = "pending_size"

        self.open_orders.append(order)
        self.order_log.append({"timestamp": timestamp.isoformat(), "order": order.to_dict()})
        return order

    def on_market_candle(self, candle: Union[Dict[str, Any], Any], latency_ms: Optional[float] = None, timestamp: Optional[datetime] = None) -> None:
        data = self._normalize_candle(candle, timestamp)
        self.last_price = data["close"]
        if data["timestamp"] is None:
            data["timestamp"] = datetime.now(timezone.utc)
        self._update_daily_reference(data["timestamp"])
        if latency_ms is not None:
            self.latency_history.append(latency_ms)
        self._process_orders(data)
        self._check_position_triggers(data)
        self._update_equity(data)
        self._update_risk(data)

    def _update_daily_reference(self, timestamp: datetime) -> None:
        current_day = normalize_timestamp_to_date(timestamp)
        if self.current_day is None or current_day != self.current_day:
            self.current_day = current_day
            self.daily_reference = self.balance + (self._unrealized_pnl(self.last_price) if self.position else 0.0)

    def _process_orders(self, candle: Dict[str, Any]) -> None:
        if not self.open_orders:
            return
        for order in list(self.open_orders):
            if order.status != "open":
                continue
            fill_price = self._determine_fill_price(order, candle)
            if fill_price is not None:
                self._fill_order(order, fill_price, candle["timestamp"])

    def _determine_fill_price(self, order: LiveOrder, candle: Dict[str, Any]) -> Optional[float]:
        side = order.side
        if order.order_type == "market":
            return candle["open"]
        if order.order_type == "limit":
            limit_price = order.limit_price if order.limit_price is not None else candle["close"]
            if side > 0 and candle["low"] <= limit_price <= candle["high"]:
                return limit_price
            if side < 0 and candle["low"] <= limit_price <= candle["high"]:
                return limit_price
            return None
        if order.order_type == "stop":
            stop_price = order.stop_price if order.stop_price is not None else candle["close"]
            if side > 0 and candle["high"] >= stop_price:
                return stop_price
            if side < 0 and candle["low"] <= stop_price:
                return stop_price
            return None
        return None

    def _fill_order(self, order: LiveOrder, price: float, timestamp: datetime) -> None:
        if order.filled_size <= 0:
            actual_size = order.requested_size
            if actual_size <= 0:
                actual_size = self._calculate_order_size(price, order.size_override)
            order.size = max(actual_size, order.size)
            order.filled_size = order.size
        order.status = "filled"
        order.filled_price = price
        order.slip_cost = self._calc_slippage(price, order.size)
        order.fee_cost = self._calc_fee(price, order.size, order.order_type)
        self.balance -= order.slip_cost + order.fee_cost
        self.open_orders.remove(order)
        self._record_execution(order, price, timestamp, "entry")
        if self.position is not None:
            self._close_position(price, timestamp, "signal_flip")
        self.position = LivePosition(
            direction=order.side,
            size=order.size,
            entry_price=price,
            entry_time=timestamp,
            stop_loss=price - order.side * self.stop_loss_pct,
            take_profit=price + order.side * self.take_profit_pct,
            breakeven_price=price,
        )

    def _check_position_triggers(self, candle: Dict[str, Any]) -> None:
        if self.position is None:
            return
        self._apply_breakeven()
        direction = self.position.direction
        close_price = candle["close"]
        exit_price = None
        reason = None
        if direction > 0:
            if candle["low"] <= self.position.stop_loss:
                exit_price = self.position.stop_loss
                reason = "stop_loss"
            elif candle["high"] >= self.position.take_profit:
                exit_price = self.position.take_profit
                reason = "take_profit"
        else:
            if candle["high"] >= self.position.stop_loss:
                exit_price = self.position.stop_loss
                reason = "stop_loss"
            elif candle["low"] <= self.position.take_profit:
                exit_price = self.position.take_profit
                reason = "take_profit"
        if reason is not None and exit_price is not None:
            self._close_position(exit_price, candle["timestamp"], reason)

    def _close_position(self, price: float, timestamp: datetime, reason: str) -> None:
        if self.position is None:
            return
        position = self.position
        slippage_cost = self._calc_slippage(price, position.size)
        fee_cost = self._calc_fee(price, position.size, "market")
        self.balance -= slippage_cost + fee_cost
        pnl = position.direction * (price - position.entry_price) * position.size
        self.balance += pnl
        self._record_execution(
            None,
            price,
            timestamp,
            reason,
            position=position,
            slippage_cost=slippage_cost,
            fee_cost=fee_cost,
            pnl=pnl,
        )
        self.position = None

    def _unrealized_pnl(self, price: Optional[float]) -> float:
        if self.position is None or price is None:
            return 0.0
        return self.position.direction * (price - self.position.entry_price) * self.position.size

    def _update_equity(self, candle: Dict[str, Any]) -> None:
        unrealized = self._unrealized_pnl(candle["close"])
        equity = self.balance + unrealized
        self.equity_curve.append(float(equity))
        self.equity_timestamps.append(candle["timestamp"])
        self.peak_equity = max(self.peak_equity, equity)
        self.open_drawdown = min(self.open_drawdown, float((equity - self.peak_equity) / max(self.peak_equity, 1.0)))

    def _update_risk(self, candle: Dict[str, Any]) -> None:
        equity = self.equity_curve[-1]
        if self.max_drawdown_pct is not None and equity <= self.peak_equity * (1.0 - self.max_drawdown_pct):
            self.emergency_stopped = self.emergency_stop_on_violation
        if self.max_daily_loss_pct is not None and self.daily_reference is not None:
            if equity <= self.daily_reference * (1.0 - self.max_daily_loss_pct):
                self.emergency_stopped = self.emergency_stop_on_violation
        if self.emergency_stopped:
            for order in list(self.open_orders):
                order.status = "cancelled"
                order.message = "emergency_stop"
                self.order_log.append({"timestamp": candle["timestamp"].isoformat(), "order": order.to_dict()})
                self.open_orders.remove(order)

    def _record_execution(
        self,
        order: Optional[LiveOrder],
        price: float,
        timestamp: datetime,
        reason: str,
        position: Optional[LivePosition] = None,
        slippage_cost: float = 0.0,
        fee_cost: float = 0.0,
        pnl: Optional[float] = None,
    ) -> None:
        record = {
            "timestamp": timestamp.isoformat(),
            "price": float(price),
            "reason": reason,
            "position": position.to_dict() if position is not None else None,
            "order": order.to_dict() if order is not None else None,
            "slippage_cost": float(slippage_cost),
            "fee_cost": float(fee_cost),
            "pnl": float(pnl) if pnl is not None else None,
            "unrealized": float(self._unrealized_pnl(price)),
            "balance": float(self.balance),
        }
        self.execution_log.append(record)

    def get_state(self) -> Dict[str, Any]:
        return {
            "balance": float(self.balance),
            "equity": float(self.equity_curve[-1]) if self.equity_curve else float(self.balance),
            "peak_equity": float(self.peak_equity),
            "drawdown": float(self.open_drawdown),
            "last_price": float(self.last_price) if self.last_price is not None else None,
            "current_position": self.position.to_dict() if self.position is not None else None,
            "positions": [self.position.to_dict()] if self.position is not None else [],
            "open_orders": [order.to_dict() for order in self.open_orders],
            "equity_curve": list(self.equity_curve),
            "equity_timestamps": [ts.isoformat() for ts in self.equity_timestamps],
            "execution_log": list(self.execution_log),
            "order_log": list(self.order_log),
            "signal_log": list(self.signal_log),
            "latency_history": list(self.latency_history),
            "total_orders": len(self.order_log),
            "total_signals": len(self.signal_log),
            "total_executions": len(self.execution_log),
            "emergency_stopped": self.emergency_stopped,
            "current_day": self.current_day.isoformat() if self.current_day is not None else None,
            "risk_management": {
                "max_daily_loss_pct": self.max_daily_loss_pct,
                "max_drawdown_pct": self.max_drawdown_pct,
                "emergency_stop_on_violation": self.emergency_stop_on_violation,
            },
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "balance": self.balance,
            "peak_equity": self.peak_equity,
            "open_drawdown": self.open_drawdown,
            "position": self.position.to_dict() if self.position is not None else None,
            "open_orders": [order.to_dict() for order in self.open_orders],
            "equity_curve": list(self.equity_curve),
            "equity_timestamps": [ts.isoformat() for ts in self.equity_timestamps],
            "execution_log": list(self.execution_log),
            "order_log": list(self.order_log),
            "signal_log": list(self.signal_log),
            "latency_history": list(self.latency_history),
            "last_price": self.last_price,
            "order_counter": self.order_counter,
            "current_day": self.current_day.isoformat() if self.current_day else None,
            "emergency_stopped": self.emergency_stopped,
            "strategy_parameters": self.strategy_parameters,
            "pine_config": self.pine_config,
            "risk_management": self.risk_management,
        }

    def restore(self, snapshot: Dict[str, Any]) -> None:
        self.balance = float(snapshot.get("balance", self.balance))
        self.peak_equity = float(snapshot.get("peak_equity", self.peak_equity))
        self.open_drawdown = float(snapshot.get("open_drawdown", self.open_drawdown))
        self.position = None
        if snapshot.get("position"):
            pos = snapshot["position"]
            entry_time = pos["entry_time"]
            if isinstance(entry_time, str):
                entry_time = datetime.fromisoformat(entry_time)
            self.position = LivePosition(
                direction=int(pos["direction"]),
                size=float(pos["size"]),
                entry_price=float(pos["entry_price"]),
                entry_time=entry_time,
                stop_loss=float(pos["stop_loss"]),
                take_profit=float(pos["take_profit"]),
                breakeven_price=float(pos["breakeven_price"]) if pos.get("breakeven_price") is not None else None,
            )
        self.open_orders = []
        self.order_counter = int(snapshot.get("order_counter", 0))
        for order_data in snapshot.get("open_orders", []):
            order = LiveOrder(
                id=int(order_data.get("id", self.order_counter)),
                side=int(order_data.get("side", 0)),
                size=float(order_data.get("size", 0.0)),
                order_type=str(order_data.get("order_type", "market")),
                limit_price=order_data.get("limit_price"),
                stop_price=order_data.get("stop_price"),
                created_at=datetime.fromisoformat(order_data.get("created_at")) if isinstance(order_data.get("created_at"), str) else order_data.get("created_at"),
                status=order_data.get("status", "open"),
                filled_price=order_data.get("filled_price"),
                filled_size=float(order_data.get("filled_size", 0.0)),
                slip_cost=float(order_data.get("slip_cost", 0.0)),
                fee_cost=float(order_data.get("fee_cost", 0.0)),
                message=order_data.get("message"),
            )
            self.open_orders.append(order)
            self.order_counter = max(self.order_counter, order.id)
        self.equity_curve = [float(v) for v in snapshot.get("equity_curve", [self.balance])]
        self.equity_timestamps = [datetime.fromisoformat(ts) for ts in snapshot.get("equity_timestamps", []) if ts]
        self.execution_log = list(snapshot.get("execution_log", []))
        self.order_log = list(snapshot.get("order_log", []))
        self.signal_log = list(snapshot.get("signal_log", []))
        self.latency_history = [float(x) for x in snapshot.get("latency_history", [])]
        self.last_price = snapshot.get("last_price", self.last_price)
        self.current_day = datetime.fromisoformat(snapshot["current_day"]) if snapshot.get("current_day") else None
        self.emergency_stopped = bool(snapshot.get("emergency_stopped", False))
        self.strategy_parameters = snapshot.get("strategy_parameters", self.strategy_parameters)
        self.pine_config = snapshot.get("pine_config", self.pine_config)
        self.risk_management = snapshot.get("risk_management", self.risk_management)

    def export_state_json(self) -> str:
        return json.dumps(self.snapshot(), default=str)
