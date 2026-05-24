from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union

import pandas as pd

from live.paper_engine import PaperTradingEngine


class MarketReplay:
    def __init__(
        self,
        candles: pd.DataFrame,
        engine: PaperTradingEngine,
        signal_source: Optional[Union[pd.Series, Dict[datetime, Any]]] = None,
        speed_multiplier: float = 1.0,
        logger: Any = None,
    ) -> None:
        self.candles = candles.copy()
        self.engine = engine
        self.signal_source = signal_source
        self.speed_multiplier = max(float(speed_multiplier), 0.001)
        self.logger = logger

    def run(self) -> Dict[str, Any]:
        if self.candles.empty:
            return self.engine.get_state()

        signals = self._normalize_signal_source()
        for timestamp, row in self.candles.iterrows():
            signal = signals.get(timestamp)
            if signal is not None:
                self.engine.process_signal(signal, timestamp)
            self.engine.on_market_candle(
                {
                    "timestamp": timestamp,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0.0)),
                },
                latency_ms=0.0,
                timestamp=timestamp,
            )
        return self.engine.get_state()

    def _normalize_signal_source(self) -> Dict[datetime, Any]:
        if self.signal_source is None:
            return {}
        if isinstance(self.signal_source, pd.Series):
            return {timestamp: signal for timestamp, signal in self.signal_source.items()}
        return dict(self.signal_source)
