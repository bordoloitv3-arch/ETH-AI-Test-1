from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union


@dataclass
class TradeRecord:
    entry_index: Union[str, int, datetime]
    exit_index: Union[str, int, datetime]
    direction: int
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    return_pct: float
    exit_reason: str
    # Detailed costs and bookkeeping
    entry_fee: Optional[float] = None
    exit_fee: Optional[float] = None
    spread_cost: Optional[float] = None
    slippage_cost: Optional[float] = None
    funding_cost: Optional[float] = None
    margin_used: Optional[float] = None
    pnl_gross: Optional[float] = None
    max_adverse_excursion: Optional[float] = None
    max_favorable_excursion: Optional[float] = None
    holding_time: Optional[float] = None
    risk_adjusted_return: Optional[float] = None
    execution_type: Optional[str] = None
    order_type: Optional[str] = None


@dataclass
class OptimizationResult:
    parameters: dict
    metrics: dict
    report_path: str
    engine: str
    trial_id: Optional[int] = None
