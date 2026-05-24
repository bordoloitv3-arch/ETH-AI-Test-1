import datetime

import numpy as np
import pandas as pd

from utils.timestamp_utils import normalize_timestamp, normalize_timestamp_to_date


def test_normalize_timestamp_with_datetime_datetime() -> None:
    ts = datetime.datetime(2026, 5, 24, 12, 34, 56)
    normalized = normalize_timestamp(ts)
    assert isinstance(normalized, datetime.datetime)
    assert normalized == ts


def test_normalize_timestamp_with_pandas_timestamp() -> None:
    ts = pd.Timestamp("2026-05-24T12:34:56Z")
    normalized = normalize_timestamp(ts)
    assert isinstance(normalized, datetime.datetime)
    assert normalized == ts.to_pydatetime()


def test_normalize_timestamp_with_numpy_datetime64() -> None:
    ts = np.datetime64("2026-05-24T12:34:56")
    normalized = normalize_timestamp(ts)
    assert isinstance(normalized, datetime.datetime)
    assert normalized == pd.to_datetime(ts).to_pydatetime()


def test_normalize_timestamp_with_integer_index_falls_back_to_numeric() -> None:
    index = pd.Index([0, 1, 2, 3], dtype=int)
    normalized = normalize_timestamp(2, index=index)
    normalized_date = normalize_timestamp_to_date(2, index=index)
    assert normalized == 2
    assert normalized_date == 2


def test_normalize_timestamp_with_replay_synthetic_integer_index() -> None:
    synthetic_index = pd.RangeIndex(start=1000, stop=1010)
    normalized = normalize_timestamp(1004, index=synthetic_index)
    normalized_date = normalize_timestamp_to_date(1004, index=synthetic_index)
    assert normalized == 1004
    assert normalized_date == 1004
