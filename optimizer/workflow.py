import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from backtester.engine import BacktestResult, FuturesBacktester
from data.market_data import MarketDataEngine, MarketDataSplit
from live.manager import LiveTradingCoordinator
from memory.sqlite_memory import SQLOptimizationMemory
from optimizer.genetic_engine import GeneticOptimizer
from optimizer.metrics import (
    objective_score,
    performance_metrics,
    robust_score,
    overfitting_score,
    robustness_rank,
)
from optimizer.optuna_engine import OptunaOptimizer
from optimizer.reporting import ReportGenerator
from optimizer.rl_engine import RLOptimizer
from pine.strategy_manager import PineStrategyManager
from optimizer.monte_carlo import MonteCarloEngine
from utils.timestamp_utils import normalize_timestamp_to_date


class WorkflowManager:
    def __init__(self, config: Any, logger: Any) -> None:
        self.config = config
        self.logger = logger
        self.memory = SQLOptimizationMemory()
        self.report_generator = ReportGenerator(output_dir=self.config.reporting.get("output_dir", "reports"))
        self.data_engine = MarketDataEngine(logger=logger)
        self.market_data = self._load_market_data()
        self.pine_strategy = self._load_pine_strategy()

    def _load_pine_strategy(self) -> Optional[PineStrategyManager]:
        pine_config = getattr(self.config, "pine_script", {})
        path = pine_config.get("path")
        if not path:
            return None
        try:
            strategy = PineStrategyManager(path, output_dir=pine_config.get("version_dir"))
            self.logger.info("Loaded Pine Script strategy from %s", path)
            return strategy
        except Exception as exc:
            self.logger.exception("Failed to load Pine Script strategy: %s", exc)
            raise

    def run(self) -> Dict[str, Any]:
        engine_name = self.config.optimizer.get("engine", "optuna")
        if self.market_data is not None:
            price_data = self.market_data.train
            self.logger.info("Using market data for optimization: %s rows", len(price_data))
        else:
            sample_length = int(self.config.backtest.get("sample_length", 252))
            price_data = self.generate_sample_price(sample_length)
            self.logger.warning("No market data configured; using generated sample series.")

        if engine_name == "optuna":
            result = self._run_optuna(price_data)
        elif engine_name == "genetic":
            result = self._run_genetic(price_data)
        elif engine_name == "rl":
            result = self._run_rl(price_data)
        else:
            raise ValueError(f"Unsupported optimizer engine: {engine_name}")

        if self.market_data is not None:
            validation_metrics, validation_equity, validation_trades, _ = self._evaluate_candidate_with_result(
                self.market_data.validation,
                result["parameters"],
                allow_oos=False,
            )
            test_metrics, test_equity, test_trades, _ = self._evaluate_candidate_with_result(
                self.market_data.test,
                result["parameters"],
                allow_oos=True,
            )
            result["dataset_metrics"] = {
                "validation": validation_metrics,
                "test": test_metrics,
            }
            result["dataset_equity"] = {
                "validation": validation_equity,
                "test": test_equity,
            }
            result["dataset_trades"] = {
                "validation": validation_trades,
                "test": test_trades,
            }

        parameter_report_paths = {}
        if self.pine_strategy is not None:
            self.logger.info("Generating Pine Script parameter extraction report.")
            parameter_report_paths = self.report_generator.generate_parameter_report(
                self.pine_strategy.parameters,
                f"{self.pine_strategy.path.stem}_parameters",
            )

        history = result.get("history") or []
        best_params = result.get("parameters") or {}
        # Begin with rejected entries from history
        rejected_parameters: List[Dict[str, Any]] = []
        for entry in history:
            if entry.get("params") != best_params:
                rejected_parameters.append({"params": entry.get("params"), "value": entry.get("value")})
        # If the final best result was marked rejected, add its reason
        if result.get("rejection_reasons"):
            rejected_parameters.append({"params": result.get("parameters"), "rejection_reasons": result.get("rejection_reasons")})
        result["rejected_parameters"] = rejected_parameters if rejected_parameters else None
        result["optimization_history"] = history

        output_paths = self.report_generator.build_report(
            trades=result["trades"],
            metrics=result["metrics"],
            equity_curve=result["equity_curve"],
            report_prefix=result["report_prefix"],
            formats=self.config.reporting.get("formats", ["csv", "json", "plot"]),
            search_history=history,
            dataset_metrics=result.get("dataset_metrics"),
            dataset_equity=result.get("dataset_equity"),
            monte_carlo=result.get("monte_carlo"),
            walk_forward_results=result.get("walk_forward"),
            rejected_parameters=rejected_parameters if rejected_parameters else None,
            best_parameters=best_params,
            oos_metrics=result.get("dataset_metrics", {}).get("test"),
        )
        output_paths["strategy_version"] = strategy_version_path
        output_paths["parameter_report"] = parameter_report_paths

        self.memory.save_run(
            engine=engine_name,
            parameters=result["parameters"],
            metrics=result["metrics"],
            validation_metrics=result.get("dataset_metrics", {}).get("validation"),
            oos_metrics=result.get("dataset_metrics", {}).get("test"),
            walk_forward_metrics=result.get("walk_forward"),
            overfitting_score=result.get("overfitting_score"),
            robustness_rank=result.get("robustness_rank"),
            rejected_parameters=rejected_parameters if rejected_parameters else None,
            optimization_history=history if history else None,
            report_path=output_paths.get("json", str(Path(self.config.reporting.get("output_dir", "reports")) / f"{result['report_prefix']}.json")),
        )

        report = {
            "report_path": output_paths,
            "best_parameters": result["parameters"],
            "metrics": result["metrics"],
        }
        if "dataset_metrics" in result:
            report["dataset_metrics"] = result["dataset_metrics"]
        if "monte_carlo" in result and result["monte_carlo"]:
            report["monte_carlo"] = result["monte_carlo"]
        return report

    def build_live_trading_coordinator(
        self,
        strategy_parameters: Optional[Dict[str, Any]] = None,
        signal_callback: Optional[Callable[[Dict[str, Any], Any], Any]] = None,
        state_directory: str = "memory/live_state",
        checkpoint_interval: int = 1,
        enable_prometheus: bool = False,
        prometheus_port: int = 8000,
        baseline_metrics: Optional[Dict[str, Any]] = None,
    ) -> LiveTradingCoordinator:
        live_risk = self.config.backtest.get("live_risk", {}) or {}
        return LiveTradingCoordinator(
            symbol=self.config.data.get("symbol", "ETHUSDT"),
            interval=self.config.data.get("live_interval", "1m"),
            strategy_parameters=strategy_parameters or {},
            pine_config=getattr(self.config, "pine_script", {}) or {},
            risk_management=live_risk,
            signal_callback=signal_callback,
            logger=self.logger,
            state_directory=state_directory,
            checkpoint_interval=checkpoint_interval,
            enable_prometheus=enable_prometheus,
            prometheus_port=prometheus_port,
            baseline_metrics=baseline_metrics,
        )

    def _build_search_space(self) -> Dict[str, Any]:
        config_space = self.config.optimizer.get("search_space", {}) or {}
        if self.pine_strategy is not None:
            strategy_space = self.pine_strategy.generate_search_space()
            merged_space = {**strategy_space, **config_space}
            return merged_space
        return config_space

    def _run_optuna(self, price_data: Union[pd.Series, pd.DataFrame]) -> Dict[str, Any]:
        search_space = self._build_search_space()
        optimizer = OptunaOptimizer(
            seed=int(self.config.optimizer.get("seed", 42)),
            sampler_type=self.config.optimizer.get("sampler", "tpe"),
        )
        jobs = int(self.config.optimizer.get("jobs", 1))

        def objective(trial: Any, params: Dict[str, Any]) -> float:
            if self.market_data is not None and self.config.optimizer.get("walk_forward", {}).get("enabled", False):
                walk_forward = self._evaluate_candidate_walk_forward(self.market_data.full, params)
                score = walk_forward["score"]
            else:
                train_metrics = self.evaluate_candidate(price_data, params)
                # optionally run monte carlo quick checks during trials to penalize fragile candidates
                mc_summary = None
                if self.config.optimizer.get("monte_carlo", {}).get("enabled", False):
                    mc_conf = self.config.optimizer.get("monte_carlo", {})
                    mc_engine = MonteCarloEngine(
                        price_data,
                        self.build_signals(
                            price_data if isinstance(price_data, pd.Series) else price_data["close"],
                            int(params.get("momentum_window", 10)),
                            float(params.get("threshold", 0.005)),
                        ),
                        backtester_kwargs=dict(self.config.backtest),
                    )
                    mc_res = mc_engine.run(
                        simulations=int(mc_conf.get("simulations", 20)),
                        seed=int(self.config.optimizer.get("seed", 42)),
                        parallel=bool(mc_conf.get("parallel", False)),
                        workers=mc_conf.get("workers", "auto"),
                        chunk_size=int(mc_conf.get("chunk_size", 100)),
                        backend=mc_conf.get("backend", "auto"),
                    )
                    mc_summary = mc_res.summary

                if self.market_data is not None and self.config.optimizer.get("use_validation_in_objective", True):
                    validation_metrics = self.evaluate_candidate(self.market_data.validation, params)
                    base_score = robust_score(
                        train_metrics,
                        validation_metrics=validation_metrics,
                        objective=self.config.optimizer.get("objective", "combined"),
                    )
                else:
                    base_score = objective_score(train_metrics, self.config.optimizer.get("objective", "combined"))

                # weight composition with optional monte carlo robustness
                weights = self.config.optimizer.get("weights", {}) or {}
                if mc_summary is not None:
                    w_sharpe = float(weights.get("sharpe", 0.35))
                    w_profit = float(weights.get("profit", 0.2))
                    w_draw = float(weights.get("drawdown", 0.2))
                    w_rob = float(weights.get("robustness", 0.25))
                    sharpe = float(train_metrics.get("sharpe_ratio", 0.0))
                    profit = float(train_metrics.get("return_pct", 0.0)) / 100.0
                    draw = float(train_metrics.get("drawdown", 0.0))
                    rob = float(mc_summary.get("robustness_score", 0.0))
                    score = w_sharpe * sharpe + w_profit * profit - w_draw * abs(draw) + w_rob * rob
                else:
                    score = float(base_score)
            self.logger.debug(f"Optuna trial {trial.number} objective score: {score}")
            return score

        best = optimizer.optimize(
            objective,
            search_space,
            trials=int(self.config.optimizer.get("trials", 30)),
            n_jobs=jobs,
        )
        metrics, equity_curve, trades, monte_carlo_stats = self.evaluate_candidate_with_result(price_data, best["best_params"])
        report_prefix = f"optuna_best_{best['best_trial']}"
        result = {
            "parameters": best["best_params"],
            "metrics": metrics,
            "equity_curve": equity_curve,
            "trades": trades,
            "report_prefix": report_prefix,
            "history": best.get("history"),
        }
        if monte_carlo_stats:
            result["monte_carlo"] = monte_carlo_stats
            result["probability_of_ruin"] = float(monte_carlo_stats.get("probability_of_ruin", 0.0))
            result["tail_risk_score"] = float(monte_carlo_stats.get("average_cvar95", 0.0))
            result["equity_stability_score"] = float(monte_carlo_stats.get("equity_stability_score", 0.0))
            # ranking fields
            result["probability_of_ruin"] = float(monte_carlo_stats.get("probability_of_ruin", 0.0))
            result["tail_risk_score"] = float(monte_carlo_stats.get("average_cvar95", 0.0))
            result["equity_stability_score"] = float(monte_carlo_stats.get("equity_stability_score", 0.0))
        if self.market_data is not None and self.config.optimizer.get("walk_forward", {}).get("enabled", False):
            result["walk_forward"] = self._evaluate_candidate_walk_forward(self.market_data.full, best["best_params"])
        # Final out-of-sample evaluation (strictly reserve final test set)
        if self.market_data is not None and getattr(self.market_data, "test", None) is not None:
            # compute validation metrics if available
            validation_metrics = None
            if self.config.optimizer.get("use_validation_in_objective", True) and getattr(self.market_data, "validation", None) is not None:
                validation_metrics, _, _, _ = self._evaluate_candidate_with_result(self.market_data.validation, best["best_params"], allow_oos=False)
            # OOS evaluation - explicit allow
            oos_metrics, oos_equity, oos_trades, _ = self._evaluate_candidate_with_result(self.market_data.test, best["best_params"], allow_oos=True)
            result["out_of_sample"] = {"metrics": oos_metrics, "equity_curve": oos_equity, "trades": oos_trades}
            result["overfitting_score"] = overfitting_score(metrics, validation_metrics, oos_metrics, self.config.optimizer.get("objective", "combined"))
            result["robustness_rank"] = robustness_rank(metrics, validation_metrics, oos_metrics, monte_carlo_stats, result.get("walk_forward"), self.config.optimizer.get("objective", "combined"))
            # Assess candidate for rejection and ranking
            assessment = self._assess_candidate(metrics, validation_metrics, oos_metrics, monte_carlo_stats, result.get("walk_forward"))
            # merge assessment fields into result for persistence and reporting
            result.update(assessment)
        return result

    def _run_genetic(self, price_data: Union[pd.Series, pd.DataFrame]) -> Dict[str, Any]:
        search_space = self._build_search_space()
        optimizer = GeneticOptimizer(
            population_size=int(self.config.optimizer.get("population_size", 20)),
            generations=int(self.config.optimizer.get("generations", 10)),
            mutation_rate=float(self.config.optimizer.get("mutation_rate", 0.2)),
            seed=int(self.config.optimizer.get("seed", 42)),
        )
        jobs = int(self.config.optimizer.get("jobs", 1))

        def objective(params: Dict[str, Any]) -> float:
            if self.market_data is not None and self.config.optimizer.get("walk_forward", {}).get("enabled", False):
                walk_forward = self._evaluate_candidate_walk_forward(self.market_data.full, params)
                return walk_forward["score"]

            train_metrics = self.evaluate_candidate(price_data, params)
            if self.market_data is not None and self.config.optimizer.get("use_validation_in_objective", True):
                validation_metrics = self.evaluate_candidate(self.market_data.validation, params)
                return robust_score(
                    train_metrics,
                    validation_metrics=validation_metrics,
                    objective=self.config.optimizer.get("objective", "combined"),
                )
            return objective_score(train_metrics, self.config.optimizer.get("objective", "combined"))

        best = optimizer.run(objective, search_space, n_jobs=jobs)
        metrics, equity_curve, trades, monte_carlo_stats = self.evaluate_candidate_with_result(price_data, best["best_params"])
        report_prefix = "genetic_best"
        result = {
            "parameters": best["best_params"],
            "metrics": metrics,
            "equity_curve": equity_curve,
            "trades": trades,
            "report_prefix": report_prefix,
            "history": best.get("history"),
        }
        if monte_carlo_stats:
            result["monte_carlo"] = monte_carlo_stats
        if self.market_data is not None and self.config.optimizer.get("walk_forward", {}).get("enabled", False):
            result["walk_forward"] = self._evaluate_candidate_walk_forward(self.market_data.full, best["best_params"])
        # Final OOS evaluation
        if self.market_data is not None and getattr(self.market_data, "test", None) is not None:
            validation_metrics = None
            if self.config.optimizer.get("use_validation_in_objective", True) and getattr(self.market_data, "validation", None) is not None:
                validation_metrics, _, _, _ = self._evaluate_candidate_with_result(self.market_data.validation, best["best_params"], allow_oos=False)
            oos_metrics, oos_equity, oos_trades, _ = self._evaluate_candidate_with_result(self.market_data.test, best["best_params"], allow_oos=True)
            result["out_of_sample"] = {"metrics": oos_metrics, "equity_curve": oos_equity, "trades": oos_trades}
            result["overfitting_score"] = overfitting_score(metrics, validation_metrics, oos_metrics, self.config.optimizer.get("objective", "combined"))
            result["robustness_rank"] = robustness_rank(metrics, validation_metrics, oos_metrics, monte_carlo_stats, result.get("walk_forward"), self.config.optimizer.get("objective", "combined"))
            assessment = self._assess_candidate(metrics, validation_metrics, oos_metrics, monte_carlo_stats, result.get("walk_forward"))
            result.update(assessment)
        return result

    def _run_rl(self, price_data: Union[pd.Series, pd.DataFrame]) -> Dict[str, Any]:
        optimizer = RLOptimizer(seed=int(self.config.optimizer.get("seed", 42)))
        policy = optimizer.train(env=None, iterations=int(self.config.optimizer.get("iterations", 500)))
        metrics, equity_curve, trades, monte_carlo_stats = self.evaluate_candidate_with_result(
            price_data,
            {
                "momentum_window": 10,
                "threshold": 0.005,
                "stop_loss_pct": float(self.config.backtest.get("stop_loss_pct", 0.02)),
                "take_profit_pct": float(self.config.backtest.get("take_profit_pct", 0.04)),
            },
        )
        report_prefix = "rl_scaffold"
        result = {
            "parameters": {"policy": policy},
            "metrics": metrics,
            "equity_curve": equity_curve,
            "trades": trades,
            "report_prefix": report_prefix,
        }
        if monte_carlo_stats:
            result["monte_carlo"] = monte_carlo_stats
            result["probability_of_ruin"] = float(monte_carlo_stats.get("probability_of_ruin", 0.0))
            result["tail_risk_score"] = float(monte_carlo_stats.get("average_cvar95", 0.0))
            result["equity_stability_score"] = float(monte_carlo_stats.get("equity_stability_score", 0.0))
        # Final OOS evaluation for RL scaffold
        if self.market_data is not None and getattr(self.market_data, "test", None) is not None:
            validation_metrics = None
            if self.config.optimizer.get("use_validation_in_objective", True) and getattr(self.market_data, "validation", None) is not None:
                validation_metrics, _, _, _ = self._evaluate_candidate_with_result(self.market_data.validation, result["parameters"], allow_oos=False)
            oos_metrics, oos_equity, oos_trades, _ = self._evaluate_candidate_with_result(self.market_data.test, result["parameters"], allow_oos=True)
            result["out_of_sample"] = {"metrics": oos_metrics, "equity_curve": oos_equity, "trades": oos_trades}
            result["overfitting_score"] = overfitting_score(metrics, validation_metrics, oos_metrics, self.config.optimizer.get("objective", "combined"))
            result["robustness_rank"] = robustness_rank(metrics, validation_metrics, oos_metrics, monte_carlo_stats, result.get("walk_forward"), self.config.optimizer.get("objective", "combined"))
            assessment = self._assess_candidate(metrics, validation_metrics, oos_metrics, monte_carlo_stats, result.get("walk_forward"))
            result.update(assessment)
        return result

    def evaluate_candidate_with_result(
        self, price_data: Union[pd.Series, pd.DataFrame], params: Dict[str, Any]
    ) -> Any:
        return self._evaluate_candidate_with_result(price_data, params, allow_oos=False)

    def _evaluate_candidate_with_result(
        self, price_data: Union[pd.Series, pd.DataFrame], params: Dict[str, Any], allow_oos: bool = False
    ) -> Any:
        # Prevent accidental access to reserved final out-of-sample test data during optimization
        if self.market_data is not None and self._is_final_test(price_data) and not allow_oos:
            raise ValueError("Access to final out-of-sample test data is forbidden during optimization.")
        backtest_res = self.run_backtest(price_data, params)
        if isinstance(backtest_res, tuple) and len(backtest_res) == 2:
            realistic_bt, ideal_bt = backtest_res
        else:
            realistic_bt = backtest_res
            ideal_bt = None

        metrics = performance_metrics(realistic_bt.equity_curve, realistic_bt.trades)
        monte_carlo_stats = None
        if self.config.optimizer.get("monte_carlo", {}).get("enabled", False):
            mc_conf = self.config.optimizer.get("monte_carlo", {})
            try:
                mc_engine = MonteCarloEngine(
                    price_data,
                    self.build_signals(
                        price_data if isinstance(price_data, pd.Series) else price_data["close"],
                        int(params.get("momentum_window", 10)),
                        float(params.get("threshold", 0.005)),
                    ),
                    backtester_kwargs=dict(self.config.backtest),
                    memory=self.memory,
                )
                monte_carlo_stats = None
                mc_res = mc_engine.run(
                    simulations=int(mc_conf.get("simulations", 20)),
                    seed=int(self.config.optimizer.get("seed", 42)),
                    parallel=bool(mc_conf.get("parallel", False)),
                    workers=mc_conf.get("workers", "auto"),
                    chunk_size=int(mc_conf.get("chunk_size", 100)),
                    backend=mc_conf.get("backend", "auto"),
                )
                monte_carlo_stats = mc_res.summary
                # attach sample equities if needed
                monte_carlo_stats["sample_equities"] = [s.tolist() for s in mc_res.sample_equities]
            except Exception:
                monte_carlo_stats = None
        return metrics, realistic_bt.equity_curve, realistic_bt.trades, monte_carlo_stats

    def _is_final_test(self, price_data: Union[pd.Series, pd.DataFrame]) -> bool:
        if self.market_data is None:
            return False
        test = getattr(self.market_data, "test", None)
        if test is None:
            return False
        try:
            # Identity or index equality check
            if price_data is test:
                return True
            if hasattr(price_data, "index") and hasattr(test, "index"):
                return price_data.index.equals(test.index)
        except Exception:
            return False
        return False

    def _load_market_data(self) -> Optional[MarketDataSplit]:
        data_config = getattr(self.config, "data", {})
        if not data_config or not data_config.get("source"):
            return None
        try:
            df = self.data_engine.load_data(
                source=data_config.get("source", "csv"),
                path=data_config.get("path"),
                symbol=data_config.get("symbol", "ETHUSDT"),
                timeframe=data_config.get("timeframe", "1m"),
                start=data_config.get("start"),
                end=data_config.get("end"),
                timestamp_col=data_config.get("timestamp_col"),
            )
            if data_config.get("gap_fill_method"):
                df = self.data_engine.handle_gaps(
                    df,
                    data_config.get("timeframe", "1m"),
                    method=data_config.get("gap_fill_method", "ffill"),
                )
            return self.data_engine.create_split_from_config(df, data_config)
        except Exception as exc:
            self.logger.exception("Failed to load market data: %s", exc)
            return None

    def _create_walk_forward_splits(self, full_df: pd.DataFrame) -> List[Dict[str, Any]]:
        config = self.config.optimizer.get("walk_forward", {})
        windows = int(config.get("windows", 3))
        train_pct = float(config.get("train_pct", 0.6))
        test_pct = float(config.get("test_pct", 0.4))

        if windows < 1:
            raise ValueError("walk_forward.windows must be at least 1.")
        if abs(train_pct + test_pct - 1.0) > 1e-6:
            raise ValueError("walk_forward train_pct and test_pct must sum to 1.0.")

        total = len(full_df)
        if total < 2:
            return []

        window_size = total // windows
        splits: List[Dict[str, Any]] = []
        for index in range(windows):
            start = index * window_size
            end = start + window_size if index < windows - 1 else total
            window = full_df.iloc[start:end]
            if len(window) < 2:
                continue

            train_end = start + int(round(len(window) * train_pct))
            if train_end <= start:
                train_end = start + 1
            if train_end >= end:
                train_end = end - 1

            train = full_df.iloc[start:train_end]
            test = full_df.iloc[train_end:end]
            if train.empty or test.empty:
                continue

            splits.append({"train": train, "test": test, "window_index": index})

        return splits

    def _evaluate_candidate_walk_forward(self, full_df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        splits = self._create_walk_forward_splits(full_df)
        if not splits:
            return {"score": 0.0, "window_results": []}

        objective_name = self.config.optimizer.get("objective", "combined")
        use_validation = self.config.optimizer.get("use_validation_in_objective", True)
        window_results: List[Dict[str, Any]] = []

        for split in splits:
            train_metrics, _, _, _ = self.evaluate_candidate_with_result(split["train"], params)
            test_metrics, _, _, _ = self.evaluate_candidate_with_result(split["test"], params)
            if use_validation:
                score = robust_score(
                    train_metrics,
                    validation_metrics=test_metrics,
                    objective=objective_name,
                )
            else:
                score = objective_score(train_metrics, objective_name)
            window_results.append(
                {
                    "window_index": split["window_index"],
                    "train_metrics": train_metrics,
                    "test_metrics": test_metrics,
                    "score": score,
                }
            )

        average_score = float(np.mean([entry["score"] for entry in window_results]))
        return {"score": average_score, "window_results": window_results}

    def evaluate_candidate(self, price_data: Union[pd.Series, pd.DataFrame] = None, *, price_series: Union[pd.Series, pd.DataFrame] = None, params: Dict[str, Any] = None) -> Dict[str, Any]:
        if price_series is not None:
            price_data = price_series
        if price_data is None or params is None:
            raise ValueError("evaluate_candidate requires price_data (or price_series) and params")
        metrics, _, _, _ = self.evaluate_candidate_with_result(price_data, params)
        return metrics

    def _assess_candidate(self, train_metrics: Dict[str, Any], validation_metrics: Optional[Dict[str, Any]], oos_metrics: Optional[Dict[str, Any]], monte_carlo_stats: Optional[Dict[str, Any]], walk_forward_results: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess candidate for rejection and ranking.

        Returns a dict with keys: rejected (bool), rejection_reasons (list), stability_rank, oos_consistency_rank, overfitting_penalty, final_ranking_score
        """
        rejection_conf = self.config.optimizer.get("rejection", {}) if getattr(self.config, "optimizer", None) else {}
        max_drawdown = float(rejection_conf.get("max_drawdown", 0.3))
        min_robustness = float(rejection_conf.get("min_robustness_score", 0.6))
        max_prob_ruin = float(rejection_conf.get("max_probability_of_ruin", 0.15))
        min_oos_sharpe = float(rejection_conf.get("min_oos_sharpe", 1.0))

        reasons: List[str] = []
        prob_ruin = float(monte_carlo_stats.get("probability_of_ruin", 0.0)) if monte_carlo_stats else 0.0
        robustness_score = float(monte_carlo_stats.get("robustness_score", 0.0)) if monte_carlo_stats else 0.0
        avg_cvar95 = float(monte_carlo_stats.get("average_cvar95", 0.0)) if monte_carlo_stats else 0.0
        equity_stability_score = float(monte_carlo_stats.get("equity_stability_score", 0.0)) if monte_carlo_stats else 0.0

        # Overfitting penalty
        of_penalty = 0.0
        try:
            of_penalty = overfitting_score(train_metrics or {}, validation_metrics, oos_metrics or {}, self.config.optimizer.get("objective", "combined"))
        except Exception:
            of_penalty = 0.0

        # OOS consistency rank from walk-forward
        oos_consistency_rank = 0.0
        if walk_forward_results and isinstance(walk_forward_results, dict):
            wf = walk_forward_results.get("window_results", [])
            if wf:
                scores = [w.get("score", 0.0) for w in wf]
                oos_consistency_rank = float(1.0 / (1.0 + float(pd.Series(scores).std()))) if pd.Series(scores).std() > 0 else 1.0

        # stability rank from monte carlo equity stability
        stability_rank = equity_stability_score

        # tail risk scoring (higher magnitude cvar -> worse)
        tail_risk_score = abs(avg_cvar95)

        # final ranking score prioritizes robustness, then oos consistency, stability, tail risk, then profit
        profit_norm = float(train_metrics.get("return_pct", 0.0)) / 100.0 if train_metrics else 0.0
        final_score = (
            robustness_score * 0.4
            + oos_consistency_rank * 0.2
            + stability_rank * 0.2
            + (1.0 - tail_risk_score) * 0.1
            + profit_norm * 0.1
        )

        # Apply rejection rules
        if prob_ruin > max_prob_ruin:
            reasons.append("high_probability_of_ruin")
        if robustness_score < min_robustness:
            reasons.append("low_robustness_score")
        if abs(train_metrics.get("drawdown", 0.0)) > max_drawdown:
            reasons.append("excessive_drawdown")
        if oos_metrics and float(oos_metrics.get("sharpe_ratio", 0.0)) < min_oos_sharpe:
            reasons.append("poor_oos_sharpe")
        if of_penalty and of_penalty > float(self.config.optimizer.get("robustness_threshold", 0.5)):
            reasons.append("overfitting_detected")
        # tail risk threshold (aggressive default)
        if tail_risk_score > float(rejection_conf.get("max_tail_risk", 0.2)):
            reasons.append("excessive_tail_risk")
        # unstable equity curves
        if stability_rank < float(rejection_conf.get("min_equity_stability", 0.3)):
            reasons.append("unstable_monte_carlo_equity")

        rejected = len(reasons) > 0

        return {
            "rejected": rejected,
            "rejection_reasons": reasons,
            "stability_rank": stability_rank,
            "oos_consistency_rank": oos_consistency_rank,
            "overfitting_penalty": float(of_penalty),
            "tail_risk_score": float(tail_risk_score),
            "probability_of_ruin": float(prob_ruin),
            "final_ranking_score": float(final_score),
        }

    def run_backtest(self, price_data: Union[pd.Series, pd.DataFrame], params: Dict[str, Any]) -> Any:
        stop_loss_pct = float(params.get("stop_loss_pct", self.config.backtest.get("stop_loss_pct", 0.02)))
        take_profit_pct = float(params.get("take_profit_pct", self.config.backtest.get("take_profit_pct", 0.04)))
        # Prepare signals and run both realistic and ideal (no-cost) simulations for comparison
        if isinstance(price_data, pd.DataFrame) and self._is_luxalgo_strategy():
            realistic = self._run_luxalgo_backtest(price_data, params, realistic=True)
            ideal = self._run_luxalgo_backtest(price_data, params, realistic=False)
            return realistic, ideal

        if isinstance(price_data, pd.DataFrame):
            price_series = price_data["close"]
        else:
            price_series = price_data

        momentum_window = int(params.get("momentum_window", 10))
        threshold = float(params.get("threshold", 0.005))
        signals = self.build_signals(price_series, momentum_window, threshold)
        backtester = FuturesBacktester(
            price_series=price_data,
            initial_balance=float(self.config.backtest.get("initial_balance", 100000.0)),
            leverage=float(self.config.backtest.get("leverage", 10.0)),
            taker_fee=float(self.config.backtest.get("taker_fee", 0.00075)),
            maker_fee=float(self.config.backtest.get("maker_fee", 0.00025)),
            slippage_pct=float(self.config.backtest.get("slippage_pct", 0.0005)),
            spread=float(self.config.backtest.get("spread", 0.0)),
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            funding_rate_per_period=float(self.config.backtest.get("funding_rate_per_period", 0.0)),
            maintenance_margin_pct=float(self.config.backtest.get("maintenance_margin_pct", 0.005)),
            fill_delay_bars=int(self.config.backtest.get("fill_delay_bars", 0)),
        )
        realistic = backtester.run(signals, realistic=True)
        ideal = backtester.run(signals, realistic=False)
        return realistic, ideal

    @staticmethod
    def build_signals(price_series: pd.Series, momentum_window: int, threshold: float) -> pd.Series:
        momentum = price_series.pct_change(periods=momentum_window).shift(1).fillna(0.0)
        signals = pd.Series(index=price_series.index, data=0)
        signals[momentum > threshold] = 1
        signals[momentum < -threshold] = -1
        return signals.astype(int)

    def _run_luxalgo_backtest(self, data: pd.DataFrame, params: Dict[str, Any], realistic: bool = True) -> BacktestResult:
        data = data.copy()
        required_columns = {"open", "high", "low", "close"}
        if not required_columns.issubset(data.columns):
            raise ValueError(f"LuxAlgo backtest requires OHLC data. Missing columns: {required_columns - set(data.columns)}")

        data["open"] = data["open"].astype(float)
        data["high"] = data["high"].astype(float)
        data["low"] = data["low"].astype(float)
        data["close"] = data["close"].astype(float)

        maxDist = float(params.get("maxDist", 37.0))
        tpPoints = float(params.get("tpPoints", 38.0))
        slPoints = float(params.get("slPoints", 34.0))
        beTrigger = float(params.get("beTrigger", 24.0))
        slCooldownMins = int(params.get("slCooldownMins", 0))
        tpCooldownMins = int(params.get("tpCooldownMins", 0))
        tlLength = int(params.get("tlLength", 24))
        tlMult = float(params.get("tlMult", 1.0))
        shortMaLen = int(params.get("shortMaLen", 3))
        longMaLen = int(params.get("longMaLen", 18))

        data["short_ma"] = data["close"].rolling(shortMaLen).mean()
        data["long_ma"] = data["close"].rolling(longMaLen).mean()
        data["atr"] = self._calculate_atr(data, tlLength)
        data["pivot_high"] = self._pivot_extreme(data["high"], tlLength, find_max=True)
        data["pivot_low"] = self._pivot_extreme(data["low"], tlLength, find_max=False)

        current_balance = float(self.config.backtest.get("initial_balance", 100000.0))
        fee_rate = float(self.config.backtest.get("taker_fee", 0.00075)) if realistic else 0.0
        slippage_pct = float(self.config.backtest.get("slippage_pct", 0.0005)) if realistic else 0.0
        spread = float(self.config.backtest.get("spread", 0.0)) if realistic else 0.0
        funding_rate = float(self.config.backtest.get("funding_rate_per_period", 0.0)) if realistic else 0.0
        leverage = float(self.config.backtest.get("leverage", 10.0))

        trades: List[Any] = []
        equity: List[float] = []
        position: Optional[Dict[str, Any]] = None
        fvgMid = float("nan")
        fvgIsNew = True
        cooldown_end = data.index[0] - pd.Timedelta(days=1)
        upper = 0.0
        lower = 0.0
        s_ph = 0.0
        s_pl = 0.0
        upos = 0
        dnos = 0
        prev_upos = 0
        prev_dnos = 0
        bullSeq = False
        bearSeq = False
        prev_short_ma = float("nan")
        prev_long_ma = float("nan")

        for bar_index, (timestamp, row) in enumerate(data.iterrows()):
            if bar_index >= 1:
                current_day = normalize_timestamp_to_date(timestamp, index=data.index)
                prior_day = normalize_timestamp_to_date(data.index[bar_index - 1], index=data.index)
                if current_day != prior_day:
                    fvgIsNew = True

            if fvgIsNew and bar_index >= 2:
                prior = data.iloc[bar_index - 2]
                prior_prev = data.iloc[bar_index - 1]
                if row["low"] > prior["high"] and prior_prev["close"] > prior["high"]:
                    fvgMid = float((row["low"] + prior["high"]) / 2.0)
                    fvgIsNew = False
                elif row["high"] < prior["low"] and prior_prev["close"] < prior["low"]:
                    fvgMid = float((row["high"] + prior["low"]) / 2.0)
                    fvgIsNew = False

            slope = float(row["atr"]) / max(tlLength, 1) * tlMult if pd.notna(row["atr"]) else 0.0
            pivot_high = pd.notna(row["pivot_high"])
            pivot_low = pd.notna(row["pivot_low"])

            if pivot_high:
                s_ph = slope
                upper = float(row["pivot_high"])
                upos = 0
            elif upper != 0.0:
                upper = upper - s_ph
                if row["close"] > upper - s_ph * tlLength:
                    upos += 1

            if pivot_low:
                s_pl = slope
                lower = float(row["pivot_low"])
                dnos = 0
            elif lower != 0.0:
                lower = lower + s_pl
                if row["close"] < lower + s_pl * tlLength:
                    dnos += 1

            longTrigger = upos > prev_upos
            shortTrigger = dnos > prev_dnos

            if not np.isnan(prev_short_ma) and not np.isnan(prev_long_ma):
                if prev_short_ma <= prev_long_ma and row["short_ma"] > row["long_ma"]:
                    bullSeq = True
                if row["short_ma"] < row["long_ma"]:
                    bearSeq = True
                if pivot_high:
                    bullSeq = False
                if pivot_low:
                    bearSeq = False

            prev_short_ma = row["short_ma"]
            prev_long_ma = row["long_ma"]
            prev_upos = upos
            prev_dnos = dnos

            inCooldown = timestamp < cooldown_end
            distCheck = pd.notna(fvgMid) and abs(row["close"] - fvgMid) <= maxDist
            canLong = (
                position is None
                and not inCooldown
                and pd.notna(fvgMid)
                and row["close"] > fvgMid
                and distCheck
                and row["short_ma"] > row["long_ma"]
                and bullSeq
                and longTrigger
            )
            canShort = (
                position is None
                and not inCooldown
                and pd.notna(fvgMid)
                and row["close"] < fvgMid
                and distCheck
                and row["short_ma"] < row["long_ma"]
                and bearSeq
                and shortTrigger
            )

            if position is None and (canLong or canShort):
                direction = 1 if canLong else -1
                # apply slippage and spread at entry when realistic
                base_price = float(row["close"])
                entry_price = float(base_price * (1 + np.sign(direction) * slippage_pct))
                # include half-spread
                entry_price = entry_price + (np.sign(direction) * (spread / 2.0))
                size = float(current_balance * leverage / max(entry_price, 1e-9))
                entry_fee = abs(size * entry_price) * fee_rate
                entry_spread_cost = abs(spread) * size
                entry_slippage_cost = abs(base_price * slippage_pct) * size
                position = {
                    "direction": direction,
                    "entry_price": entry_price,
                    "size": size,
                    "entry_fee": entry_fee,
                    "entry_spread_cost": entry_spread_cost if realistic else 0.0,
                    "entry_slippage_cost": entry_slippage_cost if realistic else 0.0,
                    "entry_index": timestamp,
                    "balance_before_entry": float(current_balance),
                    "be_activated": False,
                    "current_sl": float(entry_price - direction * slPoints),
                }
                # deduct entry costs
                current_balance -= (entry_fee + (entry_spread_cost if realistic else 0.0) + (entry_slippage_cost if realistic else 0.0))

            if position is not None:
                direction = int(position["direction"])
                entry_price = position["entry_price"]
                current_sl = float(position["current_sl"])
                be_activated = bool(position["be_activated"])
                exit_reason = None

                if direction > 0:
                    if not be_activated and row["high"] >= entry_price + beTrigger:
                        be_activated = True
                        current_sl = entry_price
                    if row["low"] <= current_sl:
                        exit_reason = "SL"
                    elif row["high"] >= entry_price + tpPoints:
                        exit_reason = "TP"
                else:
                    if not be_activated and row["low"] <= entry_price - beTrigger:
                        be_activated = True
                        current_sl = entry_price
                    if row["high"] >= current_sl:
                        exit_reason = "SL"
                    elif row["low"] <= entry_price - tpPoints:
                        exit_reason = "TP"

                position["current_sl"] = current_sl
                position["be_activated"] = be_activated

                if exit_reason is None:
                    unrealized = current_balance + direction * (row["close"] - entry_price) * position["size"]
                    # apply funding fee per bar
                    if realistic and funding_rate:
                        funding = position["size"] * row["close"] * funding_rate * (-np.sign(direction))
                        position.setdefault("funding_accum", 0.0)
                        position["funding_accum"] += funding
                        current_balance -= funding
                    equity.append(float(unrealized))
                else:
                    base_exit = (current_sl if exit_reason == "SL" else entry_price + direction * tpPoints)
                    exit_price = float(base_exit * (1 - np.sign(direction) * slippage_pct))
                    # include half-spread on exit
                    exit_price = exit_price - (np.sign(direction) * (spread / 2.0))
                    gross_pnl = direction * (exit_price - entry_price) * position["size"]
                    exit_fee = abs(position["size"] * exit_price) * fee_rate
                    exit_spread_cost = abs(spread) * position["size"]
                    exit_slippage_cost = abs(base_exit * slippage_pct) * position["size"]
                    funding_accum = position.get("funding_accum", 0.0)
                    realized = gross_pnl - position.get("entry_fee", 0.0) - exit_fee - exit_spread_cost - exit_slippage_cost + funding_accum
                    current_balance += realized
                    trade = TradeRecord(
                        entry_index=position["entry_index"],
                        exit_index=timestamp,
                        direction=direction,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        size=position["size"],
                        pnl=float(realized),
                        return_pct=float(realized / max(position["balance_before_entry"], 1.0)),
                        exit_reason=exit_reason,
                    )
                    trades.append(trade)
                    position = None
                    cooldown_duration = slCooldownMins if exit_reason == "SL" else tpCooldownMins
                    cooldown_end = timestamp + pd.Timedelta(minutes=cooldown_duration)
                    equity.append(float(current_balance))
            else:
                equity.append(float(current_balance))

        if position is not None:
            final_row = data.iloc[-1]
            last_price = float(final_row["close"])
            exit_price = float(last_price * (1 - np.sign(position["direction"]) * slippage_pct))
            gross_pnl = position["direction"] * (exit_price - position["entry_price"]) * position["size"]
            exit_fee = abs(position["size"] * exit_price) * fee_rate
            current_balance += gross_pnl - exit_fee
            trade = TradeRecord(
                entry_index=position["entry_index"],
                exit_index=data.index[-1],
                direction=int(position["direction"]),
                entry_price=position["entry_price"],
                exit_price=exit_price,
                size=position["size"],
                pnl=float(gross_pnl - position["entry_fee"] - exit_fee),
                return_pct=float((gross_pnl - position["entry_fee"] - exit_fee) / max(position["balance_before_entry"], 1.0)),
                exit_reason="end_of_series",
            )
            trades.append(trade)
            equity.append(float(current_balance))

        equity_series = pd.Series(equity, index=data.index[: len(equity)])
        stats = {
            "final_balance": float(equity_series.iloc[-1]),
            "return_pct": float((equity_series.iloc[-1] / equity_series.iloc[0] - 1.0) * 100.0),
            "max_drawdown": float(self._max_drawdown(equity_series)),
            "trade_count": float(len(trades)),
        }
        return BacktestResult(equity_curve=equity_series, trades=trades, stats=stats)

    def _is_luxalgo_strategy(self) -> bool:
        return self.pine_strategy is not None and self.pine_strategy.path.stem.lower().startswith("luxalgo")

    def _run_monte_carlo(self, equity_curve: pd.Series) -> Dict[str, float]:
        returns = equity_curve.pct_change().dropna()
        if returns.empty:
            return {}

        simulations = int(self.config.optimizer.get("monte_carlo", {}).get("simulations", 20))
        rng = np.random.default_rng(int(self.config.optimizer.get("seed", 42)))
        results: List[Dict[str, float]] = []
        for _ in range(max(1, simulations)):
            sample = returns.sample(frac=1.0, replace=True, random_state=int(rng.integers(0, 2**31)))
            simulated = equity_curve.iloc[0] * (1.0 + sample).cumprod()
            results.append(
                {
                    "return_pct": float((simulated.iloc[-1] / simulated.iloc[0] - 1.0) * 100.0),
                    "max_drawdown": float(self._max_drawdown(simulated)),
                    "sharpe_ratio": float(sample.mean() / sample.std() * np.sqrt(252)) if sample.std() else 0.0,
                }
            )

        average_return = float(np.mean([entry["return_pct"] for entry in results]))
        average_drawdown = float(np.mean([entry["max_drawdown"] for entry in results]))
        average_sharpe = float(np.mean([entry["sharpe_ratio"] for entry in results]))
        return {
            "average_return_pct": average_return,
            "average_max_drawdown": average_drawdown,
            "average_sharpe_ratio": average_sharpe,
        }

    @staticmethod
    def _calculate_atr(data: pd.DataFrame, period: int) -> pd.Series:
        high_low = data["high"] - data["low"]
        high_close = (data["high"] - data["close"].shift()).abs()
        low_close = (data["low"] - data["close"].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return true_range.rolling(window=max(period, 1)).mean()

    @staticmethod
    def _pivot_extreme(series: pd.Series, length: int, find_max: bool = True) -> pd.Series:
        pivot_values: List[Optional[float]] = [None] * len(series)
        values = series.to_numpy(dtype=float)
        for idx in range(length, len(values) - length):
            window = values[idx - length : idx + length + 1]
            if np.isnan(window).any():
                continue
            center = window[length]
            if find_max:
                if center == window.max() and np.count_nonzero(window == center) == 1:
                    pivot_values[idx] = float(center)
            else:
                if center == window.min() and np.count_nonzero(window == center) == 1:
                    pivot_values[idx] = float(center)
        return pd.Series(pivot_values, index=series.index)

    @staticmethod
    def _max_drawdown(series: pd.Series) -> float:
        peak = series.cummax()
        drawdown = (series - peak) / peak
        return float(drawdown.min())

    @staticmethod
    def build_signals(price_series: pd.Series, momentum_window: int, threshold: float) -> pd.Series:
        momentum = price_series.pct_change(periods=momentum_window).shift(1).fillna(0.0)
        signals = pd.Series(index=price_series.index, data=0)
        signals[momentum > threshold] = 1
        signals[momentum < -threshold] = -1
        return signals.astype(int)

    @staticmethod
    def generate_sample_price(length: int = 252) -> pd.Series:
        rng = np.random.default_rng(seed=42)
        returns = rng.normal(loc=0.0005, scale=0.02, size=length)
        prices = 1000.0 * np.exp(np.cumsum(returns))
        return pd.Series(prices, index=pd.RangeIndex(start=0, stop=length, step=1))
