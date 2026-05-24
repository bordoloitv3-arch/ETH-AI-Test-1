from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from utils.timestamp_utils import normalize_timestamp_to_date
from utils.types import TradeRecord


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: List[TradeRecord]
    stats: Dict[str, float]
    execution_report: Optional[Dict[str, Any]] = None


class FuturesBacktester:
    def __init__(
        self,
        price_series: Union[pd.Series, pd.DataFrame],
        initial_balance: float = 100000.0,
        leverage: float = 10.0,
        taker_fee: float = 0.00075,
        maker_fee: float = 0.00025,
        slippage_pct: float = 0.0005,
        spread: float = 0.0,
        stop_loss_pct: float = 0.02,
        take_profit_pct: float = 0.04,
        funding_rate_per_period: float = 0.0,
        maintenance_margin_pct: float = 0.005,
        fill_delay_bars: int = 1,
        size_mode: str = "leverage",
        fixed_size: Optional[float] = None,
        risk_pct: float = 0.01,
        volatility_window: int = 14,
        max_position_size: Optional[float] = None,
        max_exposure_pct: Optional[float] = None,
        daily_loss_limit_pct: Optional[float] = None,
        partial_fill_pct: float = 1.0,
        execution_uncertainty: float = 0.0,
        random_seed: Optional[int] = None,
        fee_rate: Optional[float] = None,
    ) -> None:
        if isinstance(price_series, pd.DataFrame):
            if "close" not in price_series.columns:
                raise ValueError("Price DataFrame must contain a close column.")
            self.price_data = price_series.copy()
            self.price_data["open"] = self.price_data["open"].astype(float)
            self.price_data["high"] = self.price_data["high"].astype(float)
            self.price_data["low"] = self.price_data["low"].astype(float)
            self.price_data["close"] = self.price_data["close"].astype(float)
            if "volume" not in self.price_data.columns:
                self.price_data["volume"] = 0.0
        else:
            self.price_data = pd.DataFrame(
                {
                    "open": price_series.astype(float),
                    "high": price_series.astype(float),
                    "low": price_series.astype(float),
                    "close": price_series.astype(float),
                },
                index=price_series.index,
            )

        self.initial_balance = initial_balance
        self.leverage = leverage
        if fee_rate is not None:
            self.taker_fee = float(fee_rate)
        else:
            self.taker_fee = taker_fee
        self.maker_fee = maker_fee
        self.slippage_pct = slippage_pct
        self.spread = spread
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.funding_rate_per_period = funding_rate_per_period
        self.maintenance_margin_pct = maintenance_margin_pct
        self.fill_delay_bars = max(1, int(fill_delay_bars))
        self.size_mode = size_mode
        self.fixed_size = fixed_size
        self.risk_pct = risk_pct
        self.volatility_window = max(1, int(volatility_window))
        self.max_position_size = max_position_size
        self.max_exposure_pct = max_exposure_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.partial_fill_pct = min(max(partial_fill_pct, 0.0), 1.0)
        self.execution_uncertainty = min(max(execution_uncertainty, 0.0), 1.0)
        self.random_seed = random_seed
        self.rng = np.random.default_rng(random_seed) if random_seed is not None else None
        self.volatility = self._calculate_volatility_series()

    def _calculate_volatility_series(self) -> pd.Series:
        returns = self.price_data["close"].pct_change().fillna(0.0)
        volatility = returns.rolling(self.volatility_window, min_periods=1).std().bfill().fillna(0.0)
        return volatility

    def _normalize_signal(self, signal: Any, default_order_type: str) -> Dict[str, Any]:
        if isinstance(signal, dict):
            return {
                "side": int(np.sign(signal.get("side", signal.get("signal", 0)))),
                "order_type": signal.get("order_type", default_order_type),
                "limit_offset_pct": float(signal.get("limit_offset_pct", 0.002)),
                "stop_offset_pct": float(signal.get("stop_offset_pct", 0.002)),
                "size_override": signal.get("size_override"),
            }
        return {
            "side": int(np.sign(signal)),
            "order_type": default_order_type,
            "limit_offset_pct": 0.002,
            "stop_offset_pct": 0.002,
            "size_override": None,
        }

    def _calculate_order_size(self, balance: float, close: float, size_override: Optional[float] = None) -> float:
        if size_override is not None and size_override > 0:
            size = float(size_override)
        elif self.size_mode == "fixed" and self.fixed_size is not None and self.fixed_size > 0:
            size = float(self.fixed_size)
        elif self.size_mode in {"risk_pct", "compound"}:
            risk_amount = max(balance * self.risk_pct, 0.0)
            risk_per_contract = max(close * self.stop_loss_pct, 1e-9)
            size = risk_amount / risk_per_contract
        elif self.size_mode == "volatility":
            vol = float(self.volatility.iloc[-1]) if not self.volatility.empty else 0.0
            risk_amount = max(balance * self.risk_pct, 0.0)
            size = risk_amount / max(vol * close, 1e-9)
        else:
            size = balance * self.leverage / max(close, 1e-9)

        if self.max_position_size is not None:
            size = min(size, float(self.max_position_size))
        if self.max_exposure_pct is not None:
            exposure_limit = max(balance * float(self.max_exposure_pct), 0.0)
            size = min(size, exposure_limit / max(close, 1e-9))
        return float(max(size, 0.0))

    def _determine_fill_price(
        self,
        order: Dict[str, Any],
        low: float,
        high: float,
        open_price: float,
        close: float,
        realistic: bool,
    ) -> Optional[float]:
        if order is None:
            return None
        order_type = order.get("order_type", "market")
        side = int(order["side"])
        if order_type == "limit":
            limit_price = order.get("limit_price")
            if limit_price is None:
                if side > 0:
                    limit_price = close * (1.0 - order.get("limit_offset_pct", 0.002))
                else:
                    limit_price = close * (1.0 + order.get("limit_offset_pct", 0.002))
            if low <= limit_price <= high:
                return float(limit_price)
            return None
        if order_type == "stop":
            stop_price = order.get("stop_price")
            if stop_price is None:
                if side > 0:
                    stop_price = close * (1.0 + order.get("stop_offset_pct", 0.002))
                else:
                    stop_price = close * (1.0 - order.get("stop_offset_pct", 0.002))
            if side > 0 and high >= stop_price:
                return float(stop_price)
            if side < 0 and low <= stop_price:
                return float(stop_price)
            return None
        return float(open_price if realistic else close)

    def _calc_fee(self, price: float, size: float, realistic: bool, order_type: str = "market") -> float:
        if not realistic:
            return 0.0
        fee_rate = self.maker_fee if order_type == "limit" else self.taker_fee
        return abs(size * price) * float(fee_rate)

    def _calc_spread_cost(self, price: float, size: float, realistic: bool) -> float:
        if not realistic or not self.spread:
            return 0.0
        return abs(self.spread) * size

    def _calc_slippage_cost(self, price: float, size: float, realistic: bool) -> float:
        if not realistic or not self.slippage_pct:
            return 0.0
        effective_slippage_pct = self.slippage_pct
        if self.execution_uncertainty and self.rng is not None:
            adjustment = self.rng.normal(0.0, self.execution_uncertainty * 0.1)
            effective_slippage_pct = max(0.0, self.slippage_pct + adjustment)
        return float(abs(price * effective_slippage_pct) * size)

    def _compute_trade_extractions(
        self,
        entry_idx: int,
        exit_idx: int,
        entry_price: float,
        direction: int,
    ) -> Dict[str, float]:
        segment = self.price_data.iloc[entry_idx : exit_idx + 1]
        if segment.empty:
            return {"mae": 0.0, "mfe": 0.0}
        if direction > 0:
            mfe = float((segment["high"] - entry_price).max())
            mae = float((segment["low"] - entry_price).min())
        else:
            mfe = float((entry_price - segment["low"]).max())
            mae = float((entry_price - segment["high"]).min())
        return {"mae": mae, "mfe": mfe}

    def _compute_holding_time(self, entry_index: Any, exit_index: Any) -> float:
        if isinstance(entry_index, datetime) and isinstance(exit_index, datetime):
            return float((exit_index - entry_index).total_seconds())
        return float(abs(self.price_data.index.get_loc(exit_index) - self.price_data.index.get_loc(entry_index)))

    def run(self, signals: pd.Series, *, order_type: str = "market", realistic: bool = True) -> BacktestResult:
        equity: List[float] = []
        trades: List[TradeRecord] = []
        current_balance = float(self.initial_balance)
        position: Optional[Dict[str, Any]] = None
        pending_order: Optional[Dict[str, Any]] = None
        daily_trading_halted = False
        current_day = None
        day_start_equity = current_balance

        prices = self.price_data.reindex(signals.index, method="ffill")

        for idx, (timestamp, signal) in enumerate(signals.items()):
            if timestamp not in prices.index:
                continue
            row = prices.loc[timestamp]
            open_price = float(row["open"])
            close = float(row["close"])
            high = float(row["high"])
            low = float(row["low"])
            signal_payload = self._normalize_signal(signal, order_type)
            side = signal_payload["side"]
            entry_order_type = signal_payload["order_type"]

            bar_day = normalize_timestamp_to_date(timestamp, index=prices.index)
            if current_day is None or bar_day != current_day:
                current_day = bar_day
                day_start_equity = current_balance
                daily_trading_halted = False

            if self.daily_loss_limit_pct is not None:
                current_equity = current_balance
                if position is not None:
                    position_unrealized = int(position["direction"]) * (close - float(position["entry_price"])) * position["size"]
                    current_equity += position_unrealized
                if current_equity <= day_start_equity * (1.0 - float(self.daily_loss_limit_pct)):
                    daily_trading_halted = True

            if pending_order is not None:
                age = idx - pending_order["created_idx"]
                if age >= self.fill_delay_bars:
                    fill_price = self._determine_fill_price(pending_order, low, high, open_price, close, realistic)
                    if fill_price is not None and pending_order["size"] > 0:
                        fill_ratio = self.partial_fill_pct
                        if self.execution_uncertainty:
                            fill_ratio = max(0.0, min(1.0, 1.0 - self.execution_uncertainty))
                        fill_size = pending_order["size"] * fill_ratio
                        remaining_size = pending_order["size"] - fill_size
                        entry_fee = self._calc_fee(fill_price, fill_size, realistic, pending_order["order_type"])
                        spread_cost = self._calc_spread_cost(fill_price, fill_size, realistic)
                        slippage_cost = self._calc_slippage_cost(fill_price, fill_size, realistic)
                        position = {
                            "direction": pending_order["side"],
                            "entry_price": fill_price,
                            "size": fill_size,
                            "entry_fee": entry_fee,
                            "created_idx": idx,
                            "entry_index": timestamp,
                            "balance_before_entry": current_balance,
                            "spread_cost": spread_cost,
                            "slippage_cost": slippage_cost,
                            "funding_accum": 0.0,
                            "order_type": pending_order["order_type"],
                        }
                        current_balance -= (entry_fee + spread_cost + slippage_cost)
                        if remaining_size <= 0 or fill_ratio >= 0.999:
                            pending_order = None
                        else:
                            pending_order["size"] = remaining_size

            if side != 0 and position is None and pending_order is None and not daily_trading_halted:
                size = self._calculate_order_size(current_balance, close, signal_payload.get("size_override"))
                if size > 0:
                    pending_order = {
                        "side": side,
                        "created_idx": idx,
                        "size": float(size),
                        "order_type": entry_order_type,
                        "limit_offset_pct": signal_payload["limit_offset_pct"],
                        "stop_offset_pct": signal_payload["stop_offset_pct"],
                    }

            if position is not None:
                direction = int(position["direction"])
                entry_price = float(position["entry_price"])
                unrealized = direction * (close - entry_price) * position["size"]
                if realistic and self.funding_rate_per_period:
                    funding_cost = position["size"] * close * self.funding_rate_per_period * (-np.sign(direction))
                    position["funding_accum"] += funding_cost
                    current_balance -= funding_cost
                exit_reason = None
                exit_price = None
                if direction > 0:
                    stop_level = entry_price - self.stop_loss_pct
                    tp_level = entry_price + self.take_profit_pct
                    if low <= stop_level:
                        exit_reason = "stop_loss"
                        exit_price = stop_level
                    elif high >= tp_level:
                        exit_reason = "take_profit"
                        exit_price = tp_level
                else:
                    stop_level = entry_price + self.stop_loss_pct
                    tp_level = entry_price - self.take_profit_pct
                    if high >= stop_level:
                        exit_reason = "stop_loss"
                        exit_price = stop_level
                    elif low <= tp_level:
                        exit_reason = "take_profit"
                        exit_price = tp_level
                if exit_reason is None and side == -direction:
                    exit_reason = "signal_flip"
                    exit_price = close
                notional = position["size"] * close
                margin_used = notional / self.leverage
                maintenance = margin_used * self.maintenance_margin_pct
                equity_margin = current_balance + unrealized
                if equity_margin <= maintenance:
                    exit_reason = "liquidation"
                    exit_price = low if direction > 0 else high
                if exit_reason is None:
                    equity.append(float(current_balance + unrealized))
                else:
                    slippage_cost = self._calc_slippage_cost(exit_price, position["size"], realistic)
                    spread_cost = self._calc_spread_cost(exit_price, position["size"], realistic)
                    exit_fee = self._calc_fee(exit_price, position["size"], realistic, position.get("order_type", "market"))
                    gross_pnl = direction * (exit_price - entry_price) * position["size"]
                    realized = gross_pnl - position.get("entry_fee", 0.0) - exit_fee - slippage_cost - spread_cost + position.get("funding_accum", 0.0)
                    current_balance += realized
                    entry_idx = self.price_data.index.get_loc(position["entry_index"])
                    extraction = self._compute_trade_extractions(entry_idx, idx, entry_price, direction)
                    holding_time = self._compute_holding_time(position["entry_index"], timestamp)
                    risk_capital = max(abs(entry_price * position["size"] / self.leverage), 1.0)
                    trade = TradeRecord(
                        entry_index=position["entry_index"],
                        exit_index=timestamp,
                        direction=direction,
                        entry_price=entry_price,
                        exit_price=float(exit_price),
                        size=position["size"],
                        pnl=float(realized),
                        return_pct=float(realized / max(position["balance_before_entry"], 1.0)),
                        exit_reason=exit_reason,
                        entry_fee=float(position.get("entry_fee", 0.0)),
                        exit_fee=float(exit_fee),
                        spread_cost=float(spread_cost),
                        slippage_cost=float(slippage_cost),
                        funding_cost=float(position.get("funding_accum", 0.0)),
                        margin_used=float(margin_used),
                        pnl_gross=float(gross_pnl),
                        max_adverse_excursion=float(extraction["mae"]),
                        max_favorable_excursion=float(extraction["mfe"]),
                        holding_time=float(holding_time),
                        risk_adjusted_return=float(realized / risk_capital),
                        execution_type="realistic" if realistic else "ideal",
                        order_type=position.get("order_type", "market"),
                    )
                    trades.append(trade)
                    position = None
                    equity.append(float(current_balance))
            else:
                equity.append(float(current_balance))

        if position is not None:
            final_row = self.price_data.iloc[-1]
            last_price = float(final_row["close"])
            direction = int(position["direction"])
            exit_price = last_price
            slippage_cost = self._calc_slippage_cost(exit_price, position["size"], realistic)
            spread_cost = self._calc_spread_cost(exit_price, position["size"], realistic)
            exit_fee = self._calc_fee(exit_price, position["size"], realistic, position.get("order_type", "market"))
            gross_pnl = direction * (exit_price - position["entry_price"]) * position["size"]
            realized = gross_pnl - position.get("entry_fee", 0.0) - exit_fee - slippage_cost - spread_cost + position.get("funding_accum", 0.0)
            current_balance += realized
            entry_idx = self.price_data.index.get_loc(position["entry_index"])
            extraction = self._compute_trade_extractions(entry_idx, len(self.price_data) - 1, position["entry_price"], direction)
            holding_time = self._compute_holding_time(position["entry_index"], self.price_data.index[-1])
            risk_capital = max(abs(position["entry_price"] * position["size"] / self.leverage), 1.0)
            trade = TradeRecord(
                entry_index=position["entry_index"],
                exit_index=self.price_data.index[-1],
                direction=direction,
                entry_price=position["entry_price"],
                exit_price=exit_price,
                size=position["size"],
                pnl=float(realized),
                return_pct=float(realized / max(position["balance_before_entry"], 1.0)),
                exit_reason="end_of_series",
                entry_fee=float(position.get("entry_fee", 0.0)),
                exit_fee=float(exit_fee),
                spread_cost=float(spread_cost),
                slippage_cost=float(slippage_cost),
                funding_cost=float(position.get("funding_accum", 0.0)),
                margin_used=float((position["size"] * exit_price) / self.leverage),
                pnl_gross=float(gross_pnl),
                max_adverse_excursion=float(extraction["mae"]),
                max_favorable_excursion=float(extraction["mfe"]),
                holding_time=float(holding_time),
                risk_adjusted_return=float(realized / risk_capital),
                execution_type="realistic" if realistic else "ideal",
                order_type=position.get("order_type", "market"),
            )
            trades.append(trade)
            if equity:
                equity[-1] = float(current_balance)
            else:
                equity.append(float(current_balance))

        equity_series = pd.Series(equity, index=prices.index[: len(equity)])
        total_fees = sum(t.entry_fee or 0.0 for t in trades) + sum(t.exit_fee or 0.0 for t in trades)
        total_slippage = sum(t.slippage_cost or 0.0 for t in trades)
        total_spread = sum(t.spread_cost or 0.0 for t in trades)
        total_funding = sum(t.funding_cost or 0.0 for t in trades)
        avg_mae = float(np.mean([t.max_adverse_excursion for t in trades if t.max_adverse_excursion is not None])) if trades else 0.0
        avg_mfe = float(np.mean([t.max_favorable_excursion for t in trades if t.max_favorable_excursion is not None])) if trades else 0.0
        avg_holding = float(np.mean([t.holding_time for t in trades if t.holding_time is not None])) if trades else 0.0
        avg_rar = float(np.mean([t.risk_adjusted_return for t in trades if t.risk_adjusted_return is not None])) if trades else 0.0
        stats = {
            "final_balance": float(equity_series.iloc[-1]) if not equity_series.empty else float(current_balance),
            "return_pct": float((equity_series.iloc[-1] / equity_series.iloc[0] - 1.0) * 100.0) if len(equity_series) > 1 else 0.0,
            "max_drawdown": float(self._max_drawdown(equity_series)) if not equity_series.empty else 0.0,
            "trade_count": float(len(trades)),
            "total_fees": float(total_fees),
            "total_slippage": float(total_slippage),
            "total_spread": float(total_spread),
            "total_funding": float(total_funding),
            "average_mae": float(avg_mae),
            "average_mfe": float(avg_mfe),
            "average_holding_time": float(avg_holding),
            "average_risk_adjusted_return": float(avg_rar),
        }
        execution_report = {
            "order_type": order_type,
            "size_mode": self.size_mode,
            "fill_delay_bars": self.fill_delay_bars,
            "partial_fill_pct": self.partial_fill_pct,
            "execution_uncertainty": self.execution_uncertainty,
            "daily_loss_limit_pct": self.daily_loss_limit_pct,
            "max_exposure_pct": self.max_exposure_pct,
        }
        return BacktestResult(equity_curve=equity_series, trades=trades, stats=stats, execution_report=execution_report)

    @staticmethod
    def _max_drawdown(series: pd.Series) -> float:
        peak = series.cummax()
        drawdown = (series - peak) / peak
        return float(drawdown.min())

        

