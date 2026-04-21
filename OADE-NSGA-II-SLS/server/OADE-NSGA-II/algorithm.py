"""
Vòng lặp tiến hoá chính của NSGA-II cải tiến.
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

import numpy as np

from .core import CreationMode, Individual, ProblemWrapper
from .operators import (
    _make_evaluated_individual,
    de_mutation,
    generate_obl_offspring,
    get_neighborhood_indices,
    initialize_from_data,
    initialize_obl,
    sbx_crossover_mutation,
    tournament_selection,
)
from .selection import environmental_selection, remove_duplicates

logger = logging.getLogger(__name__)


class OADE_NSGAII:
    """NSGA-II cải tiến với DE thích nghi, OBL và partial restart khi trì trệ."""

    def __init__(self, problem: ProblemWrapper, pop_size: int = 100, n_gen: int = 100) -> None:
        self.problem = problem
        self.pop_size = pop_size
        self.n_gen = n_gen
        self.n_var = problem.n_var
        self.n_obj = problem.n_obj
        self.xl = problem.xl
        self.xu = problem.xu

        self.mean_F = 0.5
        self.mean_CR = 0.5
        self.prob_de = 0.5

        min_neighbors = 10 if self.n_obj >= 3 else 5
        self.n_neighbors = max(min_neighbors, int(pop_size * 0.15))

        self.pc = 0.9
        self.pm = 1.0 / (self.n_var * np.log(max(pop_size, 2)))
        self.eta_c = 20.0
        self.eta_m = 20.0

        self.stagnation_patience = n_gen // 4
        self.stagnation_tolerance = 1e-4
        self.restart_elite_ratio = 0.3

        self.population: List[Individual] = []
        self.history: List[np.ndarray] = []

    def run(
        self,
        initial_x: Optional[np.ndarray] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> np.ndarray:
        """Chạy thuật toán và trả về ma trận F của quần thể cuối."""
        self.population = self._build_initial_population(initial_x)
        self.history.clear()

        last_ideal = None
        stagnation_counter = 0

        for gen in range(self.n_gen):
            stagnation_counter, last_ideal = self._check_and_handle_stagnation(
                stagnation_counter, last_ideal
            )

            offspring = self._generate_offspring(gen)
            self._evaluate_unevaluated(offspring)

            combined = remove_duplicates(self.population + offspring)
            combined = self._fill_if_too_small(combined)
            self.population = environmental_selection(combined, self.pop_size, self.n_obj)

            self._update_adaptive_parameters(offspring)
            self.history.append(np.array([ind.F for ind in self.population]))

            if progress_callback is not None:
                progress_callback(gen + 1, self.n_gen)

        return np.array([ind.F for ind in self.population])

    def _build_initial_population(self, initial_x: Optional[np.ndarray]) -> List[Individual]:
        if initial_x is not None:
            pop = initialize_from_data(self.problem, initial_x)
            return environmental_selection(pop, self.pop_size, self.n_obj)
        return initialize_obl(self.problem, self.pop_size)

    def _generate_offspring(self, gen: int) -> List[Individual]:
        neighbor_indices = get_neighborhood_indices(self.population, self.n_neighbors)

        offspring = [self._create_one_child(i, neighbor_indices) for i in range(self.pop_size)]

        if gen % 10 == 0:
            offspring += generate_obl_offspring(self.population, self.problem, self.xl, self.xu)

        return offspring

    def _create_one_child(self, idx: int, neighbor_indices: np.ndarray) -> Individual:
        if np.random.rand() < self.prob_de:
            return de_mutation(
                idx,
                self.population,
                neighbor_indices,
                self.xl,
                self.xu,
                self.n_var,
                self.mean_F,
                self.mean_CR,
            )
        return sbx_crossover_mutation(
            tournament_selection(self.population),
            tournament_selection(self.population),
            self.xl,
            self.xu,
            self.n_var,
            self.pc,
            self.pm,
            self.eta_c,
            self.eta_m,
        )

    def _evaluate_unevaluated(self, offspring: List[Individual]) -> None:
        unevaluated = [ind for ind in offspring if ind.F is None]
        if not unevaluated:
            return

        x_batch = np.array([ind.X for ind in unevaluated])
        f_batch = self.problem.evaluate(x_batch)
        for ind, f in zip(unevaluated, f_batch):
            ind.F = f.flatten().copy()

    def _check_and_handle_stagnation(
        self, stagnation_counter: int, last_ideal: Optional[np.ndarray]
    ) -> tuple[int, np.ndarray]:
        current_ideal = np.min([ind.F for ind in self.population], axis=0)

        if last_ideal is not None:
            improved = np.linalg.norm(current_ideal - last_ideal) >= self.stagnation_tolerance
            stagnation_counter = 0 if improved else stagnation_counter + 1

        if stagnation_counter >= self.stagnation_patience:
            self._partial_restart()
            stagnation_counter = 0

        return stagnation_counter, current_ideal

    def _partial_restart(self) -> None:
        n_keep = int(self.pop_size * self.restart_elite_ratio)
        logger.info(
            "Stagnation detected; partial restart — keeping top %d individuals (%d%%).",
            n_keep,
            int(self.restart_elite_ratio * 100),
        )
        elite = self.population[:n_keep]

        n_new = self.pop_size - n_keep
        x_new = self.xl + np.random.rand(n_new, self.n_var) * (self.xu - self.xl)
        f_new = self.problem.evaluate(x_new)
        new_inds = [_make_evaluated_individual(x_new[i], f_new[i]) for i in range(n_new)]

        self.population = environmental_selection(elite + new_inds, self.pop_size, self.n_obj)
        self.mean_F = self.mean_CR = 0.5

    def _fill_if_too_small(self, population: List[Individual]) -> List[Individual]:
        missing = self.pop_size - len(population)
        if missing <= 0:
            return population

        x_fill = self.xl + np.random.rand(missing, self.n_var) * (self.xu - self.xl)
        f_fill = self.problem.evaluate(x_fill)
        extras = [_make_evaluated_individual(x_fill[i], f_fill[i]) for i in range(missing)]
        return population + extras

    def _update_adaptive_parameters(self, offspring: List[Individual]) -> None:
        de_offspring = [ind for ind in offspring if ind.creation_mode == CreationMode.DE]
        sbx_offspring = [ind for ind in offspring if ind.creation_mode == CreationMode.SBX]
        successful_de = [ind for ind in de_offspring if ind.rank == 1]

        total = len(de_offspring) + len(sbx_offspring)
        if total > 0:
            de_ratio = len(de_offspring) / total
            self.prob_de = float(np.clip(0.9 * self.prob_de + 0.1 * de_ratio, 0.2, 0.8))

        if successful_de:
            f_values = np.array([ind.used_F for ind in successful_de])
            cr_values = np.array([ind.used_CR for ind in successful_de])
            mean_f = float(np.mean(f_values))
            # Guard against division by zero before computing Lehmer mean.
            if mean_f > 0:
                lehmer_mean_F = float(np.mean(f_values**2) / mean_f)
                self.mean_F = 0.9 * self.mean_F + 0.1 * lehmer_mean_F
            self.mean_CR = 0.9 * self.mean_CR + 0.1 * float(np.mean(cr_values))