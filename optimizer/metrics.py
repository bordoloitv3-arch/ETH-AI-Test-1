from math import sqrt
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

from utils.types import TradeRecord


def net_profit(equity_curve: pd.Series) -> float:
    return float(equity_curve.iloc[-1] - equity_curve.iloc[0])


def return_pct(equity_curve: pd.Series) -> float:
    if equity_curve.iloc[0] == 0:
        return 0.0
    return float((equity_curve.iloc[-1] / equity_curve.iloc[0] - 1.0) * 100.0)


def returns(equity_curve: pd.Series) -> pd.Series:
    return equity_curve.pct_change().fillna(0.0)


def sharpe_ratio(equity_curve: pd.Series, risk_free_rate: float = 0.0) -> float:
    ret = returns(equity_curve)
    mean = float(ret.mean() - risk_free_rate / 252)
    volatility = float(ret.std())
    if volatility == 0:
        return 0.0
    return float(mean / volatility * sqrt(252))


def downside_deviation(equity_curve: pd.Series, target: float = 0.0) -> float:
    ret = returns(equity_curve)
    downside = ret[ret < target]
    if downside.empty:
        return 0.0
    return float(np.sqrt(np.mean(np.square(downside - target))))


def sortino_ratio(equity_curve: pd.Series, risk_free_rate: float = 0.0) -> float:
    ret = returns(equity_curve)
    downside = downside_deviation(equity_curve, risk_free_rate / 252)
    if downside == 0:
        return 0.0
    excess = float(ret.mean() - risk_free_rate / 252)
    return float(excess / downside * sqrt(252))


def drawdown(equity_curve: pd.Series) -> float:
    peak = equity_curve.cummax()
    trough = equity_curve / peak - 1.0
    return float(trough.min())


def equity_stability(equity_curve: pd.Series) -> float:
    ret = returns(equity_curve)
    volatility = float(ret.std())
    if volatility <= 0:
        return 0.0
    return float(1.0 / (1.0 + volatility))


def win_rate(trades: List[TradeRecord]) -> float:
    if not trades:
        return 0.0
    winners = sum(1 for trade in trades if trade.pnl > 0)
    return float(winners / len(trades))


def profit_factor(trades: List[TradeRecord]) -> float:
    gross_profit = sum(trade.pnl for trade in trades if trade.pnl > 0)
    gross_loss = abs(sum(trade.pnl for trade in trades if trade.pnl < 0))
    if gross_loss == 0:
        return float(gross_profit) if gross_profit > 0 else 0.0
    return float(gross_profit / gross_loss)


def recovery_factor(equity_curve: pd.Series) -> float:
    max_dd = abs(drawdown(equity_curve))
    total_return = net_profit(equity_curve)
    if max_dd == 0:
        return float(total_return) if total_return > 0 else 0.0
    return float(total_return / max_dd)


def performance_score(metrics: Dict[str, float]) -> float:
    return (
        metrics.get("sharpe_ratio", 0.0) * 0.4
        + metrics.get("return_pct", 0.0) * 0.02
        + metrics.get("profit_factor", 0.0) * 0.2
        - abs(metrics.get("drawdown", 0.0)) * 0.5
        + metrics.get("equity_stability", 0.0) * 5.0
    )


def objective_score(metrics: Dict[str, float], objective: str = "combined") -> float:
    objective = str(objective or "combined").lower()
    if objective == "sharpe":
        return metrics.get("sharpe_ratio", 0.0)
    if objective == "profit_factor":
        return metrics.get("profit_factor", 0.0)
    if objective == "return_pct":
        return metrics.get("return_pct", 0.0)
    if objective == "drawdown":
        return -abs(metrics.get("drawdown", 0.0))
    if objective == "recovery_factor":
        return metrics.get("recovery_factor", 0.0)
    if objective == "win_rate":
        return metrics.get("win_rate", 0.0)
    return performance_score(metrics)


def robust_score(
    metrics: Dict[str, float],
    validation_metrics: Optional[Dict[str, float]] = None,
    test_metrics: Optional[Dict[str, float]] = None,
    objective: str = "combined",
) -> float:
    scores: List[float] = [objective_score(metrics, objective)]
    if validation_metrics:
        scores.append(objective_score(validation_metrics, objective))
    if test_metrics:
        scores.append(objective_score(test_metrics, objective))
    return float(sum(scores) / len(scores))


def performance_metrics(equity_curve: pd.Series, trades: List[TradeRecord]) -> Dict[str, float]:
    return {
        "net_profit": net_profit(equity_curve),
        "return_pct": return_pct(equity_curve),
        "sharpe_ratio": sharpe_ratio(equity_curve),
        "sortino_ratio": sortino_ratio(equity_curve),
        "drawdown": drawdown(equity_curve),
        "equity_stability": equity_stability(equity_curve),
        "win_rate": win_rate(trades),
        "profit_factor": profit_factor(trades),
        "recovery_factor": recovery_factor(equity_curve),
        "trade_count": float(len(trades)),
    }


def optimization_score(metrics: Dict[str, float]) -> float:
    return performance_score(metrics)


def overfitting_score(train_metrics: Dict[str, float], validation_metrics: Optional[Dict[str, float]], oos_metrics: Dict[str, float], objective: str = "combined") -> float:
    """Return a normalized overfitting score: positive means overfitting (train > oos)."""
    train_score = objective_score(train_metrics, objective)
    oos_score = objective_score(oos_metrics, objective)
    diff = train_score - oos_score
    if diff <= 0:
        return 0.0
    denom = max(abs(train_score), 1e-6)
    return float(diff / denom)


def robustness_rank(
    train_metrics: Dict[str, float],
    validation_metrics: Optional[Dict[str, float]],
    oos_metrics: Dict[str, float],
    monte_carlo_stats: Optional[Dict[str, float]] = None,
    walk_forward_results: Optional[Dict[str, Any]] = None,
    objective: str = "combined",
) -> float:
    base = robust_score(train_metrics, validation_metrics=validation_metrics, test_metrics=oos_metrics, objective=objective)
    of = overfitting_score(train_metrics, validation_metrics, oos_metrics, objective)
    stability = oos_metrics.get("equity_stability", 0.0)
    mc_sharpe = 0.0
    if monte_carlo_stats:
        mc_sharpe = float(monte_carlo_stats.get("average_sharpe_ratio", 0.0))
    wf_score = 0.0
    if walk_forward_results and isinstance(walk_forward_results, dict):
        wf_windows = walk_forward_results.get("window_results", [])
        if wf_windows:
            wf_score = float(np.mean([w.get("score", 0.0) for w in wf_windows]))
    composite = base - of * 0.5 + stability * 0.5 + mc_sharpe * 0.2 + wf_score * 0.2
    return float(composite)
