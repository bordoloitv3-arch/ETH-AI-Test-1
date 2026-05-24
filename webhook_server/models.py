from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, validator


class TradingViewAlert(BaseModel):
    symbol: str
    timeframe: Optional[str]
    signal: str
    strategy: Optional[str]
    params: Optional[Dict[str, Any]] = Field(default_factory=dict)
    timestamp: Optional[Any]
    price: Optional[float]
    risk: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @validator("signal")
    def signal_must_be_known(cls, v: str) -> str:
        allowed = {"LONG", "SHORT", "CLOSE", "STOP"}
        if v.upper() not in allowed:
            raise ValueError(f"Unsupported signal: {v}")
        return v.upper()
