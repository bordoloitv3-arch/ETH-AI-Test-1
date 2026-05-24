import pandas as pd

from data.market_data import MarketDataEngine


def test_market_data_engine_normalizes_and_detects_missing_candles() -> None:
    df = pd.DataFrame(
        {
            "timestamp": [
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:01:00Z",
                "2024-01-01T00:03:00Z",
                "2024-01-01T00:04:00Z",
            ],
            "open": [100.0, 101.0, 103.0, 104.0],
            "high": [101.0, 102.0, 104.0, 105.0],
            "low": [99.5, 100.5, 102.5, 103.5],
            "close": [101.0, 102.0, 104.0, 105.0],
            "volume": [10.0, 12.0, 8.0, 9.0],
        }
    )

    engine = MarketDataEngine()
    normalized = engine._normalize_dataframe(df)
    missing = engine.detect_missing_candles(normalized, "1m")

    assert normalized.index.freq is None or normalized.index.is_monotonic_increasing
    assert len(missing) == 1
    assert missing[0].isoformat() == "2024-01-01T00:02:00+00:00"


def test_market_data_engine_split_data() -> None:
    rng = pd.date_range("2024-01-01T00:00:00Z", periods=10, freq="1min")
    df = pd.DataFrame(
        {
            "open": [1.0 + i for i in range(10)],
            "high": [1.0 + i + 0.5 for i in range(10)],
            "low": [1.0 + i - 0.5 for i in range(10)],
            "close": [1.0 + i for i in range(10)],
            "volume": [100.0 for _ in range(10)],
        },
        index=rng,
    )

    engine = MarketDataEngine()
    split = engine.split_data(df, train_pct=0.5, validation_pct=0.3, test_pct=0.2)

    assert len(split.train) == 5
    assert len(split.validation) == 3
    assert len(split.test) == 2
    assert split.full.shape == df.shape
