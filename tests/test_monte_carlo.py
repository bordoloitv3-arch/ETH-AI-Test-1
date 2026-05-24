import numpy as np
import pandas as pd
import pytest

from optimizer.monte_carlo import MonteCarloEngine
from memory.sqlite_memory import SQLOptimizationMemory


def make_simple_price(n=200):
    # simulate simple random walk price
    rng = np.random.default_rng(42)
    r = rng.normal(0, 0.001, size=n)
    p = 100 * np.exp(np.cumsum(r))
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.Series(p, index=idx)


def make_signals(price):
    # simple intraday signal: buy when momentum positive
    returns = price.pct_change().fillna(0)
    sig = (returns > 0).astype(int) - (returns < 0).astype(int)
    return sig


def test_reproducible_seed():
    price = make_simple_price(100)
    sig = make_signals(price)
    mc1 = MonteCarloEngine(price, sig)
    mc2 = MonteCarloEngine(price, sig)
    r1 = mc1.run(simulations=10, seed=123)
    r2 = mc2.run(simulations=10, seed=123)
    assert list(r1.simulation_metrics["final_balance"]) == list(r2.simulation_metrics["final_balance"])


def test_randomization_ranges():
    price = make_simple_price(80)
    sig = make_signals(price)
    mc = MonteCarloEngine(price, sig)
    res = mc.run(simulations=20, seed=7, base_slippage=0.001, base_spread=0.0005, base_fee=0.0005)
    # ensure sampled slippage/spread/fee are within reasonable bounds
    assert (res.simulation_metrics["slippage"] >= 0).all()
    assert (res.simulation_metrics["spread"] >= 0).all()
    assert (res.simulation_metrics["fee"] >= 0).all()


def test_robustness_score_bounds():
    price = make_simple_price(120)
    sig = make_signals(price)
    mem = SQLOptimizationMemory(database_path=":memory:")
    mc = MonteCarloEngine(price, sig, memory=mem)
    res = mc.run(simulations=30, seed=99)
    assert "robustness_score" in res.summary
    assert 0.0 <= res.summary["robustness_score"] <= 1.0


def test_parallel_reproducible_seed():
    price = make_simple_price(100)
    sig = make_signals(price)
    mc1 = MonteCarloEngine(price, sig)
    mc2 = MonteCarloEngine(price, sig)
    r1 = mc1.run(simulations=20, seed=123, parallel=True, workers=2, chunk_size=5)
    r2 = mc2.run(simulations=20, seed=123, parallel=True, workers=2, chunk_size=5)
    assert list(r1.simulation_metrics["final_balance"]) == list(r2.simulation_metrics["final_balance"])


def test_serial_and_parallel_match():
    price = make_simple_price(120)
    sig = make_signals(price)
    mc = MonteCarloEngine(price, sig)
    serial = mc.run(simulations=20, seed=321, parallel=False)
    parallel = mc.run(simulations=20, seed=321, parallel=True, workers=2, chunk_size=5)
    assert list(serial.simulation_metrics["final_balance"]) == list(parallel.simulation_metrics["final_balance"])
    assert serial.summary["robustness_score"] == pytest.approx(parallel.summary["robustness_score"], rel=1e-9)


def test_parallel_fallback_to_serial(monkeypatch):
    price = make_simple_price(60)
    sig = make_signals(price)
    mc = MonteCarloEngine(price, sig)

    def _fail(*args, **kwargs):
        raise RuntimeError("Simulated pool failure")

    monkeypatch.setattr(mc, "_execute_parallel", lambda payloads, workers, backend, chunk_size: _fail())
    result = mc.run(simulations=10, seed=456, parallel=True, workers=2)
    assert result.summary["parallel_fallback"] is True
    assert len(result.simulation_metrics) == 10
