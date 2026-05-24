import random
from multiprocessing.dummy import Pool as ThreadPool
from typing import Any, Callable, Dict, List, Optional


class GeneticOptimizer:
    def __init__(
        self,
        population_size: int = 20,
        generations: int = 10,
        mutation_rate: float = 0.2,
        seed: int = 42,
    ) -> None:
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.rng = random.Random(seed)

    def run(
        self,
        objective: Callable[[Dict[str, Any]], float],
        search_space: Dict[str, List[Any]],
        n_jobs: int = 1,
    ) -> Dict[str, Any]:
        population = self._initialize_population(search_space)
        best_candidate = None
        best_score = float("-inf")
        history: List[Dict[str, Any]] = []

        for _ in range(self.generations):
            if n_jobs > 1:
                with ThreadPool(processes=n_jobs) as pool:
                    scores = pool.map(objective, population)
            else:
                scores = [objective(candidate) for candidate in population]

            scored = [(candidate, score) for candidate, score in zip(population, scores)]
            scored.sort(key=lambda item: item[1], reverse=True)
            for candidate, score in scored:
                history.append({"params": candidate, "value": float(score)})

            if scored and scored[0][1] > best_score:
                best_candidate, best_score = scored[0]

            elite = [candidate for candidate, _ in scored[: max(1, len(scored) // 4)]]
            population = self._create_next_generation(elite, search_space)

        return {
            "best_params": best_candidate,
            "best_value": best_score,
            "history": history,
        }

    def _initialize_population(self, search_space: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        population = []
        for _ in range(self.population_size):
            candidate = {key: self.rng.choice(values) for key, values in search_space.items()}
            population.append(candidate)
        return population

    def _create_next_generation(self, elite: List[Dict[str, Any]], search_space: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        next_population = elite.copy()
        while len(next_population) < self.population_size:
            parent_a = self.rng.choice(elite)
            parent_b = self.rng.choice(elite)
            child = self._crossover(parent_a, parent_b)
            child = self._mutate(child, search_space)
            next_population.append(child)
        return next_population

    def _crossover(self, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        child = {}
        for key in a.keys():
            child[key] = a[key] if self.rng.random() < 0.5 else b[key]
        return child

    def _mutate(self, candidate: Dict[str, Any], search_space: Dict[str, List[Any]]) -> Dict[str, Any]:
        for key, values in search_space.items():
            if self.rng.random() < self.mutation_rate:
                candidate[key] = self.rng.choice(values)
        return candidate
