from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class MarketDataSplit:
    full: pd.DataFrame
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    timeframe: str


class MarketDataEngine:
    TIMEFRAME_MAP = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "1h": "1h",
        "4h": "4h",
        "1H": "1h",
        "4H": "4h",
        "1d": "1d",
        "daily": "1d",
        "Daily": "1d",
    }

    BINANCE_INTERVAL_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }

    BINANCE_FUTURES_API = "https://fapi.binance.com/api/v3/klines"

    def __init__(self, logger: Any = None) -> None:
        self.logger = logger

    def load_data(
        self,
        source: str,
        path: Optional[str] = None,
        symbol: Optional[str] = None,
        timeframe: str = "1m",
        start: Optional[str] = None,
        end: Optional[str] = None,
        timestamp_col: Optional[str] = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        source = source.lower()
        if source == "csv":
            if not path:
                raise ValueError("CSV source requires a valid path.")
            df = self.load_csv(path, timestamp_col=timestamp_col)
        elif source == "parquet":
            if not path:
                raise ValueError("Parquet source requires a valid path.")
            df = self.load_parquet(path, timestamp_col=timestamp_col)
        elif source in {"binance", "binance_futures", "binancefutures"}:
            symbol = symbol or "ETHUSDT"
            df = self.load_binance(symbol, timeframe, start=start, end=end)
        else:
            raise ValueError(f"Unsupported data source: {source}")

        if timeframe and timeframe not in self.TIMEFRAME_MAP:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        df = self.clean_data(df)
        return self.resample(df, timeframe)

    def load_csv(self, path: str, timestamp_col: Optional[str] = None) -> pd.DataFrame:
        source_path = Path(path)
        if not source_path.exists():
            raise FileNotFoundError(f"CSV file not found: {source_path}")

        df = pd.read_csv(source_path)
        return self._normalize_dataframe(df, timestamp_col)

    def load_parquet(self, path: str, timestamp_col: Optional[str] = None) -> pd.DataFrame:
        source_path = Path(path)
        if not source_path.exists():
            raise FileNotFoundError(f"Parquet file not found: {source_path}")

        df = pd.read_parquet(source_path)
        return self._normalize_dataframe(df, timestamp_col)

    def load_binance(
        self,
        symbol: str = "ETHUSDT",
        timeframe: str = "1m",
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        interval = self.BINANCE_INTERVAL_MAP.get(timeframe, timeframe)
        if interval not in self.BINANCE_INTERVAL_MAP.values():
            raise ValueError(f"Unsupported Binance timeframe: {timeframe}")
        start_time = self._parse_time_string(start)
        end_time = self._parse_time_string(end)

        rows: List[List[Any]] = []
        next_start = int(start_time.timestamp() * 1000) if start_time else None
        current_end = int(end_time.timestamp() * 1000) if end_time else None

        while True:
            params: Dict[str, Any] = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            }
            if next_start is not None:
                params["startTime"] = next_start
            if current_end is not None:
                params["endTime"] = current_end

            query = urllib.parse.urlencode(params)
            url = f"{self.BINANCE_FUTURES_API}?{query}"
            if self.logger:
                self.logger.debug("Downloading Binance futures klines: %s", url)

            with urllib.request.urlopen(url, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))

            if not payload:
                break

            rows.extend(payload)
            if len(payload) < limit:
                break

            last_ts = int(payload[-1][0])
            next_start = last_ts + 1

            if current_end and next_start >= current_end:
                break

        df = pd.DataFrame(rows, columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume",
            "ignore",
        ])
        df = df[["open_time", "open", "high", "low", "close", "volume"]]
        df = df.rename(columns={"open_time": "timestamp"})
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)
        return self._normalize_dataframe(df)

    def _normalize_dataframe(self, df: pd.DataFrame, timestamp_col: Optional[str] = None) -> pd.DataFrame:
        df = df.copy()
        df.columns = [str(col).strip().lower() for col in df.columns]

        if timestamp_col:
            ts_col = timestamp_col.strip().lower()
        else:
            ts_col = self._find_timestamp_column(df.columns)

        if ts_col not in df.columns:
            raise ValueError("Unable to identify timestamp column in market data.")

        df = df.rename(columns={ts_col: "timestamp"})
        df["timestamp"] = self._parse_timestamp_column(df["timestamp"])
        df = df.set_index("timestamp")
        df = df.sort_index()

        rename_map = {
            "open_price": "open",
            "high_price": "high",
            "low_price": "low",
            "close_price": "close",
            "volume_": "volume",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        if "open" not in df.columns or "high" not in df.columns or "low" not in df.columns or "close" not in df.columns:
            raise ValueError("Market data must contain open, high, low, and close columns.")

        if "volume" not in df.columns:
            df["volume"] = 0.0

        df = df[["open", "high", "low", "close", "volume"]]
        return df

    def _find_timestamp_column(self, columns: List[str]) -> str:
        candidates = ["timestamp", "time", "date", "datetime", "open_time"]
        for candidate in candidates:
            if candidate in columns:
                return candidate
        raise ValueError("Could not infer timestamp column from CSV or Parquet file.")

    def _parse_timestamp_column(self, series: pd.Series) -> pd.DatetimeIndex:
        if pd.api.types.is_integer_dtype(series) or pd.api.types.is_float_dtype(series):
            return pd.to_datetime(series, unit="ms", utc=True)
        return pd.to_datetime(series, utc=True)

    def resample(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        offset = self.TIMEFRAME_MAP.get(timeframe, timeframe)
        if offset not in self.TIMEFRAME_MAP.values() and offset not in {"1h", "4h", "1d", "1min", "5min", "15min"}:
            raise ValueError(f"Unsupported resample timeframe: {timeframe}")

        aggregated = df.resample(offset).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        return aggregated.dropna()

    def clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df = df[~df.index.duplicated(keep="last")]
        df = df.sort_index()
        if df.isnull().any(axis=None):
            df["close"] = df["close"].ffill()
            df["open"] = df["open"].fillna(df["close"])
            df["high"] = df["high"].fillna(df["close"])
            df["low"] = df["low"].fillna(df["close"])
            df["volume"] = df["volume"].fillna(0.0)
        return df.dropna(subset=["open", "high", "low", "close"])

    def detect_missing_candles(self, df: pd.DataFrame, timeframe: str) -> pd.DatetimeIndex:
        freq = self.TIMEFRAME_MAP.get(timeframe, timeframe)
        expected = pd.date_range(start=df.index[0], end=df.index[-1], freq=freq, tz=timezone.utc)
        missing = expected.difference(df.index)
        return missing

    def handle_gaps(self, df: pd.DataFrame, timeframe: str, method: str = "ffill") -> pd.DataFrame:
        freq = self.TIMEFRAME_MAP.get(timeframe, timeframe)
        expected = pd.date_range(start=df.index[0], end=df.index[-1], freq=freq, tz=timezone.utc)
        df = df.reindex(expected)
        if method == "ffill":
            df["close"] = df["close"].ffill()
            df["open"] = df["open"].fillna(df["close"])
            df["high"] = df["high"].fillna(df["close"])
            df["low"] = df["low"].fillna(df["close"])
            df["volume"] = df["volume"].fillna(0.0)
        return df.dropna(subset=["open", "high", "low", "close"])

    def split_data(
        self,
        df: pd.DataFrame,
        train_pct: float = 0.6,
        validation_pct: float = 0.2,
        test_pct: float = 0.2,
        timeframe: str = "1m",
    ) -> MarketDataSplit:
        if abs(train_pct + validation_pct + test_pct - 1.0) > 1e-6:
            raise ValueError("Train, validation, and test splits must sum to 1.0.")

        total = len(df)
        if total < 3:
            raise ValueError("Not enough data points to split into train/validation/test sets.")

        train_end = int(total * train_pct)
        validation_end = train_end + int(total * validation_pct)
        train = df.iloc[:train_end]
        validation = df.iloc[train_end:validation_end]
        test = df.iloc[validation_end:]

        return MarketDataSplit(
            full=df,
            train=train,
            validation=validation,
            test=test,
            timeframe=timeframe,
        )

    def create_split_from_config(self, df: pd.DataFrame, config: Dict[str, Any]) -> MarketDataSplit:
        return self.split_data(
            df,
            train_pct=float(config.get("train_pct", 0.6)),
            validation_pct=float(config.get("validation_pct", 0.2)),
            test_pct=float(config.get("test_pct", 0.2)),
            timeframe=config.get("timeframe", "1m"),
        )

    @staticmethod
    def _parse_time_string(value: Optional[str]) -> Optional[datetime]:
        if value is None:
            return None
        return pd.to_datetime(value, utc=True).to_pydatetime()
