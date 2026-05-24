from typing import Any, Callable, Dict, List


class OptunaOptimizer:
    def __init__(self, seed: int = 42, sampler_type: str = "tpe") -> None:
        self.seed = seed
        self.sampler_type = sampler_type.lower()

    def _build_sampler(self) -> Any:
        import optuna

        if self.sampler_type == "random":
            return optuna.samplers.RandomSampler(seed=self.seed)
        if self.sampler_type == "cmaes":
            return optuna.samplers.CmaEsSampler(seed=self.seed)
        return optuna.samplers.TPESampler(seed=self.seed)

    def optimize(
        self,
        objective: Callable[[Any, Dict[str, Any]], float],
        search_space: Dict[str, List[Any]],
        trials: int = 30,
        n_jobs: int = 1,
    ) -> Dict[str, Any]:
        import optuna

        sampler = self._build_sampler()
        study = optuna.create_study(direction="maximize", sampler=sampler)
        history: List[Dict[str, Any]] = []

        def wrapped(trial: Any) -> float:
            params = {}
            for key, choices in search_space.items():
                if isinstance(choices, list) and len(choices) > 0:
                    params[key] = trial.suggest_categorical(key, choices)
                else:
                    raise ValueError(f"Search space for {key} must be a non-empty list.")
            value = objective(trial, params)
            history.append({"trial": trial.number, "params": params, "value": float(value)})
            return value

        study.optimize(wrapped, n_trials=trials, n_jobs=n_jobs)
        return {
            "best_params": study.best_params,
            "best_value": study.best_value,
            "best_trial": study.best_trial.number,
            "history": history,
        }
