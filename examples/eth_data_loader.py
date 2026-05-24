from pathlib import Path

from data.market_data import MarketDataEngine


def main() -> None:
    engine = MarketDataEngine()
    data = engine.load_binance(
        symbol="ETHUSDT",
        timeframe="1m",
        start="2024-01-01T00:00:00Z",
        end="2024-02-01T00:00:00Z",
    )

    output_path = Path("data/ethusdt_1m_sample.parquet")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data.to_parquet(output_path)
    print(f"Saved ETHUSDT futures sample dataset to {output_path}")


if __name__ == "__main__":
    main()
