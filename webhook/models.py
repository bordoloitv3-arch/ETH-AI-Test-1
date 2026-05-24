from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, validator


class RiskSettings(BaseModel):
    position_side: Optional[str] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    risk_pct: Optional[float] = None


class TradingViewAlertPayload(BaseModel):
    symbol: str
    timeframe: str
    signal: str
    strategy_name: str
    strategy_parameters: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime
    price: float
    risk_settings: Optional[RiskSettings] = None
    direction: Optional[str] = None
    order_type: Optional[str] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"

    @validator("signal")
    def normalize_signal(cls, value: str) -> str:
        return value.strip().upper()

    @validator("timestamp", pre=True)
    def parse_timestamp(cls, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            if value > 10**12:
                return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        raise ValueError("Unable to parse timestamp")

    @validator("symbol")
    def uppercase_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @validator("timeframe")
    def normalize_timeframe(cls, value: str) -> str:
        return value.strip().lower()

    @validator("direction")
    def normalize_direction(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip().upper()
        if value in {"LONG", "SHORT", "NONE"}:
            return value
        return value
