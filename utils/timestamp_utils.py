from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd


def normalize_timestamp(ts: Any, index: Optional[pd.Index] = None) -> Any:
    """Normalize common timestamp-like values for robust date handling.

    This helper supports pandas.Timestamp, datetime.datetime, numpy.datetime64,
    and numeric timestamp keys. Numeric timestamps are resolved using available
    index metadata when provided. If no date semantics can be inferred, the
    original numeric key is returned unchanged.
    """
    if isinstance(ts, datetime):
        return ts

    if isinstance(ts, pd.Timestamp):
        return ts.to_pydatetime()

    if isinstance(ts, np.datetime64):
        return pd.to_datetime(ts).to_pydatetime()

    if isinstance(ts, (int, float)):
        if index is not None:
            try:
                if ts in index:
                    index_value = index[index.get_loc(ts)]
                    if isinstance(index_value, (int, float, np.integer, np.floating)):
                        return ts
                    return normalize_timestamp(index_value)
                if isinstance(index, pd.DatetimeIndex):
                    return pd.Timestamp(ts).to_pydatetime()
            except Exception:
                pass

        if ts >= 10**12:
            return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)

        if ts >= 0:
            return datetime.fromtimestamp(ts, tz=timezone.utc)

        return ts

    if isinstance(ts, str):
        parsed = pd.to_datetime(ts, errors="coerce")
        if parsed is not pd.NaT:
            return parsed.to_pydatetime()

    raise TypeError(f"Unsupported timestamp type: {type(ts)}")


def normalize_timestamp_to_date(ts: Any, index: Optional[pd.Index] = None) -> Any:
    """Return a date-like normalized timestamp for daily boundaries.

    If a datetime-like value is provided, this returns a date object.
    If a numeric index is used, the numeric key is preserved.
    """
    normalized = normalize_timestamp(ts, index=index)
    if isinstance(normalized, datetime):
        return normalized.date()
    return normalized
