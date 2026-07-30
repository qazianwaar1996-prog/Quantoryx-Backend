# evolution/genetic_optimizer.py
"""
Quantoryx Genetic Algorithm Strategy Evolver.

Evolves strategy parameters automatically over generations:
  - Each "chromosome" = a set of strategy parameters
  - Fitness = Sharpe ratio from backtest
  - Selection = top 30% survive
  - Crossover = mix two parents' parameters
  - Mutation = random parameter perturbation
  - Elitism = best individual always survives

No human tuning needed. The platform finds the optimal parameters
for any strategy on any pair/timeframe automatically.

This is what separates Quantoryx from every retail platform.
Renaissance Technologies runs something similar with billions.
"""

import random
import copy
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

from utils.logging_config import get_logger
logger = get_logger("evolution.genetic_optimizer")


@dataclass
class Chromosome:
    """A single candidate solution (parameter set)."""
    genes: Dict[str, Any]      # parameter name → value
    fitness: float = -999.0    # Sharpe ratio from backtest
    generation: int = 0
    id: str = ""


@dataclass
class EvolutionResult:
    """Final result of the genetic optimization run."""
    best_params: Dict[str, Any]
    best_fitness: float
    best_generation: int
    generations_run: int
    population_size: int
    fitness_history: List[float]     # best fitness per generation
    avg_fitness_history: List[float]
    total_backtests_run: int
    improvement_pct: float           # % improvement over default params


# ── Parameter space definitions per strategy ──────────────────────────────────
PARAM_SPACES: Dict[str, Dict[str, Dict]] = {
    "macd": {
        "fast_period":   {"type": "int",   "min": 5,    "max": 20},
        "slow_period":   {"type": "int",   "min": 20,   "max": 50},
        "signal_period": {"type": "int",   "min": 5,    "max": 15},
    },
    "rsi": {
        "period":      {"type": "int",   "min": 7,    "max": 21},
        "oversold":    {"type": "float", "min": 20.0, "max": 40.0, "step": 1.0},
        "overbought":  {"type": "float", "min": 60.0, "max": 80.0, "step": 1.0},
    },
    "bollinger": {
        "period":   {"type": "int",   "min": 10,  "max": 30},
        "std_dev":  {"type": "float", "min": 1.5, "max": 3.0, "step": 0.1},
    },
    "supertrend": {
        "period":     {"type": "int",   "min": 5,   "max": 20},
        "multiplier": {"type": "float", "min": 1.5, "max": 5.0, "step": 0.1},
    },
    "stochastic": {
        "k_period":   {"type": "int",   "min": 5,   "max": 21},
        "d_period":   {"type": "int",   "min": 2,   "max": 5},
        "oversold":   {"type": "float", "min": 15.0,"max": 30.0,"step": 1.0},
        "overbought": {"type": "float", "min": 70.0,"max": 85.0,"step": 1.0},
    },
    "momentum": {
        "roc_period": {"type": "int",   "min": 10,  "max": 40},
        "ema_period": {"type": "int",   "min": 30,  "max": 100},
        "threshold":  {"type": "float", "min": 0.1, "max": 1.0, "step": 0.05},
    },
    "ema_crossover": {
        "fast_period": {"type": "int", "min": 5,  "max": 25},
        "slow_period": {"type": "int", "min": 20, "max": 100},
    },
    "mean_reversion": {
        "period":  {"type": "int",   "min": 20,  "max": 100},
        "entry_z": {"type": "float", "min": 1.5, "max": 3.5, "step": 0.1},
    },
    "triple_ema": {
        "fast":   {"type": "int", "min": 5,  "max": 15},
        "medium": {"type": "int", "min": 15, "max": 35},
        "slow":   {"type": "int", "min": 40, "max": 100},
    },
    "volatility_breakout": {
        "ema_period":  {"type": "int",   "min": 10, "max": 30},
        "atr_period":  {"type": "int",   "min": 7,  "max": 21},
        "kc_mult":     {"type": "float", "min": 1.0,"max": 3.0,"step": 0.1},
    },
}


class GeneticStrategyOptimizer:
    """
    Genetic algorithm optimizer for any registered strategy.

    Usage:
        optimizer = GeneticStrategyOptimizer(
            strategy_name="supertrend",
            df=historical_ohlcv,
            population_size=50,
            generations=30,
        )
        result = optimizer.evolve()
        print(result.best_params)
    """

    def __init__(
        self,
        strategy_name: str,
        df: pd.DataFrame,
        population_size: int = 40,
        generations: int = 25,
        elite_pct: float = 0.10,
        mutation_rate: float = 0.20,
        crossover_rate: float = 0.70,
        fitness_fn: Optional[Callable] = None,
    ):
        self.strategy_name  = strategy_name.lower()
        self.df             = df
        self.pop_size       = population_size
        self.generations    = generations
        self.elite_pct      = elite_pct
        self.mutation_rate  = mutation_rate
        self.crossover_rate = crossover_rate
        self.fitness_fn     = fitness_fn or self._default_fitness
        self._backtests     = 0

        if self.strategy_name not in PARAM_SPACES:
            raise ValueError(
                f"No parameter space defined for '{strategy_name}'. "
                f"Available: {list(PARAM_SPACES)}"
            )
        self.param_space = PARAM_SPACES[self.strategy_name]

    def evolve(self) -> EvolutionResult:
        """Run the full genetic optimization. Returns the best parameters found."""
        logger.info("Starting genetic evolution: strategy=%s pop=%d gen=%d",
                    self.strategy_name, self.pop_size, self.generations)

        # Evaluate default params as baseline
        default_params = {k: (v["min"] + v["max"]) / 2 for k, v in self.param_space.items()}
        baseline_fitness = self.fitness_fn(default_params)

        population = self._init_population()
        self._evaluate_population(population)
        best_fitness_history = []
        avg_fitness_history  = []
        best_individual      = max(population, key=lambda c: c.fitness)

        for gen in range(self.generations):
            # Selection + reproduction
            parents   = self._select(population)
            offspring = []

            while len(offspring) < self.pop_size - int(self.pop_size * self.elite_pct):
                if random.random() < self.crossover_rate and len(parents) >= 2:
                    p1, p2 = random.sample(parents, 2)
                    child  = self._crossover(p1, p2, gen)
                else:
                    child = copy.deepcopy(random.choice(parents))

                if random.random() < self.mutation_rate:
                    child = self._mutate(child)

                child.generation = gen + 1
                offspring.append(child)

            # Elitism: keep best individuals
            n_elite = max(1, int(self.pop_size * self.elite_pct))
            elites  = sorted(population, key=lambda c: c.fitness, reverse=True)[:n_elite]
            population = elites + offspring

            # Evaluate new individuals
            self._evaluate_population(population, skip_evaluated=True)

            gen_best = max(population, key=lambda c: c.fitness)
            gen_avg  = float(np.mean([c.fitness for c in population if c.fitness > -999]))

            best_fitness_history.append(gen_best.fitness)
            avg_fitness_history.append(gen_avg)

            if gen_best.fitness > best_individual.fitness:
                best_individual = copy.deepcopy(gen_best)

            logger.info("Gen %d/%d | Best: %.4f | Avg: %.4f | Backtests: %d",
                        gen + 1, self.generations, gen_best.fitness, gen_avg, self._backtests)

        improvement = ((best_individual.fitness - baseline_fitness) / abs(baseline_fitness) * 100
                       if baseline_fitness != 0 else 0.0)

        return EvolutionResult(
            best_params=best_individual.genes,
            best_fitness=round(best_individual.fitness, 4),
            best_generation=best_individual.generation,
            generations_run=self.generations,
            population_size=self.pop_size,
            fitness_history=best_fitness_history,
            avg_fitness_history=avg_fitness_history,
            total_backtests_run=self._backtests,
            improvement_pct=round(improvement, 2),
        )

    # ─── Private ────────────────────────────────────────────────────────────

    def _init_population(self) -> List[Chromosome]:
        pop = []
        for i in range(self.pop_size):
            genes = {}
            for param, spec in self.param_space.items():
                genes[param] = self._random_gene(spec)
            pop.append(Chromosome(genes=genes, id=f"gen0_{i}"))
        return pop

    def _random_gene(self, spec: Dict) -> Any:
        if spec["type"] == "int":
            return random.randint(int(spec["min"]), int(spec["max"]))
        step = spec.get("step", 0.01)
        steps = int((spec["max"] - spec["min"]) / step)
        return round(spec["min"] + random.randint(0, steps) * step, 4)

    def _evaluate_population(self, population: List[Chromosome], skip_evaluated: bool = False):
        for c in population:
            if skip_evaluated and c.fitness > -999:
                continue
            c.fitness = self.fitness_fn(c.genes)
            self._backtests += 1

    def _select(self, population: List[Chromosome]) -> List[Chromosome]:
        """Tournament selection — top 50% by fitness."""
        sorted_pop = sorted(population, key=lambda c: c.fitness, reverse=True)
        return sorted_pop[:max(2, len(sorted_pop) // 2)]

    def _crossover(self, p1: Chromosome, p2: Chromosome, gen: int) -> Chromosome:
        """Uniform crossover — each gene randomly from either parent."""
        genes = {}
        for key in self.param_space:
            genes[key] = p1.genes[key] if random.random() < 0.5 else p2.genes[key]
        return Chromosome(genes=genes, generation=gen, id=f"gen{gen}_cross")

    def _mutate(self, c: Chromosome) -> Chromosome:
        """Gaussian mutation on a randomly selected gene."""
        c = copy.deepcopy(c)
        param = random.choice(list(self.param_space))
        spec  = self.param_space[param]
        if spec["type"] == "int":
            rng = max(1, (spec["max"] - spec["min"]) // 4)
            c.genes[param] = int(np.clip(
                c.genes[param] + random.randint(-rng, rng),
                spec["min"], spec["max"]
            ))
        else:
            step  = spec.get("step", 0.01)
            sigma = (spec["max"] - spec["min"]) * 0.1
            new   = c.genes[param] + random.gauss(0, sigma)
            c.genes[param] = round(
                float(np.clip(new, spec["min"], spec["max"])) // step * step, 4
            )
        return c

    def _default_fitness(self, params: Dict) -> float:
        """
        Default fitness function: Sharpe ratio from simple backtest.
        Penalises strategies with < 20 trades (insufficient sample).
        """
        try:
            from strategies import get_strategy
            strategy = get_strategy(self.strategy_name, params)
            result   = strategy.run(self.df.copy())

            if "signal" not in result.columns:
                return -999.0

            close   = result["close"] if "close" in result.columns else result["Close"]
            returns = close.pct_change()
            sig     = result["signal"].shift(1).fillna(0)
            strat_r = (returns * sig).dropna()

            n_trades = int((sig.diff().abs() > 0).sum())
            if n_trades < 20:
                return -1.0  # penalise insufficient trades

            mean = float(strat_r.mean())
            std  = float(strat_r.std())
            if std == 0:
                return 0.0

            sharpe = mean / std * np.sqrt(252)
            return round(sharpe, 6)
        except Exception as e:
            logger.debug("Fitness eval error: %s", e)
            return -999.0
