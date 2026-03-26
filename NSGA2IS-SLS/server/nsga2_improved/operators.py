"""
Các toán tử tiến hoá: khởi tạo, đột biến, lai ghép, OBL, chọn lọc.
"""

from __future__ import annotations

import math
import random
from typing import List

import numpy as np

from .core import CreationMode, Individual, ProblemWrapper
from .selection import environmental_selection


def _first_primes(count: int) -> np.ndarray:
    primes: list[int] = []
    candidate = 2

    while len(primes) < count:
        is_prime = True
        for prime in primes:
            if prime * prime > candidate:
                break
            if candidate % prime == 0:
                is_prime = False
                break

        if is_prime:
            primes.append(candidate)

        candidate += 1

    return np.array(primes, dtype=np.int64)


def _van_der_corput(n: int, base: int) -> np.ndarray:
    sequence = np.empty(n, dtype=np.float64)

    for index in range(n):
        value = 0.0
        denominator = 1.0
        number = index + 1

        while number > 0:
            number, remainder = divmod(number, base)
            denominator *= base
            value += remainder / denominator

        sequence[index] = value

    return sequence


def _halton_sequence(n: int, n_var: int) -> np.ndarray:
    bases = _first_primes(n_var)
    sequence = np.column_stack([_van_der_corput(n, int(base)) for base in bases])
    shift = np.random.rand(n_var)
    return np.mod(sequence + shift, 1.0)


def _latin_hypercube_sequence(n: int, n_var: int) -> np.ndarray:
    intervals = (np.arange(n, dtype=np.float64)[:, None] + np.random.rand(n, n_var)) / float(n)
    result = np.empty_like(intervals)

    for dimension in range(n_var):
        result[:, dimension] = intervals[np.random.permutation(n), dimension]

    return result


def _scale_unit_interval(samples: np.ndarray, xl: np.ndarray, xu: np.ndarray) -> np.ndarray:
    return xl + samples * (xu - xl)


def _pairwise_distances(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    diff = a[:, None, :] - b[None, :, :]
    return np.sqrt(np.sum(diff * diff, axis=2))


def _sample_in_bounds(n: int, n_var: int, xl: np.ndarray, xu: np.ndarray, use_sobol: bool) -> np.ndarray:
    """Lấy n điểm trong [xl, xu] bằng Sobol (mặc định) hoặc Latin Hypercube."""
    if use_sobol:
        n_rounded = 2 ** math.ceil(math.log2(max(n, 2)))
        raw = _halton_sequence(n_rounded, n_var)[:n]
    else:
        raw = _latin_hypercube_sequence(n, n_var)

    return _scale_unit_interval(raw, xl, xu)


def initialize_obl(problem: ProblemWrapper, pop_size: int, use_gobl: bool = True, use_sobol: bool = True) -> List[Individual]:
    """Sinh quần thể ban đầu bằng Quasi-Opposition Based Learning + Sobol/LHS."""
    xl, xu = problem.xl, problem.xu

    x_primary = _sample_in_bounds(pop_size, problem.n_var, xl, xu, use_sobol)

    if use_gobl:
        k = np.random.uniform(0.0, 1.0, size=x_primary.shape)
        x_opposite = k * (xl + xu) - x_primary
    else:
        mid = (xl + xu) / 2.0
        r = np.random.uniform(xl, mid, size=x_primary.shape)
        x_opposite = r + mid - x_primary

    x_all = np.clip(np.vstack([x_primary, x_opposite]), xl, xu)
    f_all = problem.evaluate(x_all)
    all_inds = [_make_evaluated_individual(x_all[i], f_all[i]) for i in range(len(x_all))]

    return environmental_selection(all_inds, target_size=pop_size, n_obj=problem.n_obj)


def initialize_from_data(problem: ProblemWrapper, initial_x: np.ndarray) -> List[Individual]:
    """Khởi tạo quần thể từ bộ dữ liệu X sẵn có (warm-start)."""
    f_all = problem.evaluate(initial_x)
    return [_make_evaluated_individual(initial_x[i], f_all[i]) for i in range(len(initial_x))]


def _make_evaluated_individual(x: np.ndarray, f: np.ndarray) -> Individual:
    """Tạo Individual với X và F đã sao chép, F được flatten về 1D."""
    ind = Individual()
    ind.X = x.copy()
    ind.F = f.flatten().copy()
    return ind


def get_neighborhood_indices(population: List[Individual], n_neighbors: int) -> np.ndarray:
    """Trả về chỉ số n_neighbors láng giềng gần nhất của mỗi cá thể."""
    F = np.array([ind.F for ind in population])
    f_min = F.min(axis=0)
    f_max = F.max(axis=0)
    spread = np.where(f_max - f_min == 0, 1e-10, f_max - f_min)
    F_norm = (F - f_min) / spread

    dists = _pairwise_distances(F_norm, F_norm)
    k = min(n_neighbors, len(population) - 1)
    return np.argpartition(dists, kth=k, axis=1)[:, :k]


def de_mutation(
    target_idx: int,
    population: List[Individual],
    neighbor_indices: np.ndarray,
    xl: np.ndarray,
    xu: np.ndarray,
    n_var: int,
    mean_F: float,
    mean_CR: float,
) -> Individual:
    """Tạo một con lai DE với chiến lược chọn ngẫu nhiên theo xác suất."""
    target = population[target_idx]
    F = float(np.clip(mean_F + 0.1 * np.tan(np.pi * (np.random.rand() - 0.5)), 0.1, 1.0))
    CR = float(np.clip(np.random.normal(mean_CR, 0.1), 0.0, 1.0))
    use_global = np.random.rand() < 0.3

    if use_global:
        r1, r2, r3 = random.sample(population, 3)
        mutant = r1.X + F * (r2.X - r3.X)
    else:
        mutant = _neighborhood_mutant(target, neighbor_indices[target_idx], population, F)

    trial = _binomial_crossover(target.X, mutant, CR, n_var)

    child = Individual()
    child.X = np.clip(trial, xl, xu)
    child.creation_mode = CreationMode.DE
    child.used_F = F
    child.used_CR = CR
    return child


def _neighborhood_mutant(
    target: Individual,
    neighbor_indices: np.ndarray,
    population: List[Individual],
    F: float,
) -> np.ndarray:
    """Tính vector đột biến DE/current-to-pbest/1 từ láng giềng."""
    neighbors = [population[i] for i in neighbor_indices]
    neighbors.sort(key=lambda ind: (ind.rank, -ind.crowding_dist))

    top_k = max(1, int(len(neighbors) * 0.2))
    x_pbest = random.choice(neighbors[:top_k])

    pool = [p for p in neighbors if p is not target] or population
    r1, r2 = random.sample(pool, 2) if len(pool) >= 2 else (pool[0], pool[0])

    return target.X + F * (x_pbest.X - target.X) + F * (r1.X - r2.X)


def _binomial_crossover(target_x: np.ndarray, mutant: np.ndarray, CR: float, n_var: int) -> np.ndarray:
    """Crossover nhị phân: lấy gene từ mutant nếu rand ≤ CR."""
    mask = np.random.rand(n_var) <= CR
    mask[np.random.randint(n_var)] = True
    return np.where(mask, mutant, target_x)


def sbx_crossover_mutation(
    p1: Individual,
    p2: Individual,
    xl: np.ndarray,
    xu: np.ndarray,
    n_var: int,
    pc: float,
    pm: float,
    eta_c: float,
    eta_m: float,
) -> Individual:
    """Lai ghép SBX rồi đột biến đa thức."""
    child = Individual()
    child.X = p1.X.copy()

    if np.random.rand() <= pc:
        child.X = _sbx_crossover(p1.X, p2.X, xl, xu, n_var, eta_c)

    child.X = _polynomial_mutation(child.X, xl, xu, n_var, pm, eta_m)
    child.creation_mode = CreationMode.SBX
    return child


def _sbx_crossover(x1: np.ndarray, x2: np.ndarray, xl: np.ndarray, xu: np.ndarray, n_var: int, eta_c: float) -> np.ndarray:
    """Áp dụng SBX crossover và trả về offspring thứ nhất."""
    child = x1.copy()
    u = np.random.rand(n_var)
    diff_mask = np.abs(x1 - x2) > 1e-14
    idx = (u <= 0.5) & diff_mask

    if not np.any(idx):
        return child

    y1, y2 = np.minimum(x1[idx], x2[idx]), np.maximum(x1[idx], x2[idx])
    yl, yu = xl[idx], xu[idx]
    u_sbx = np.random.rand(np.sum(idx))

    beta = 1.0 + 2.0 * (y1 - yl) / (y2 - y1)
    alpha = 2.0 - beta ** (-(eta_c + 1.0))

    betaq = np.empty_like(u_sbx)
    lo = u_sbx <= 1.0 / alpha
    betaq[lo] = (u_sbx[lo] * alpha[lo]) ** (1.0 / (eta_c + 1.0))
    betaq[~lo] = (1.0 / (2.0 - u_sbx[~lo] * alpha[~lo])) ** (1.0 / (eta_c + 1.0))

    child[idx] = np.clip(0.5 * (y1 + y2 - betaq * (y2 - y1)), yl, yu)
    return child


def _polynomial_mutation(x: np.ndarray, xl: np.ndarray, xu: np.ndarray, n_var: int, pm: float, eta_m: float) -> np.ndarray:
    """Áp dụng polynomial mutation và trả về vector đã đột biến."""
    mutated = x.copy()
    mut_mask = np.random.rand(n_var) <= pm
    if not np.any(mut_mask):
        return mutated

    y = x[mut_mask]
    yl, yu = xl[mut_mask], xu[mut_mask]
    delta1 = (y - yl) / (yu - yl)
    delta2 = (yu - y) / (yu - yl)
    mut_pow = 1.0 / (eta_m + 1.0)
    u = np.random.rand(len(y))
    deltaq = np.empty_like(y)

    lo = u <= 0.5
    if np.any(lo):
        val = 2.0 * u[lo] + (1.0 - 2.0 * u[lo]) * (1.0 - delta1[lo]) ** (eta_m + 1.0)
        deltaq[lo] = val ** mut_pow - 1.0

    hi = ~lo
    if np.any(hi):
        val = 2.0 * (1.0 - u[hi]) + 2.0 * (u[hi] - 0.5) * (1.0 - delta2[hi]) ** (eta_m + 1.0)
        deltaq[hi] = 1.0 - val ** mut_pow

    mutated[mut_mask] = np.clip(y + deltaq * (yu - yl), yl, yu)
    return mutated


def generate_obl_offspring(
    population: List[Individual],
    problem: ProblemWrapper,
    xl: np.ndarray,
    xu: np.ndarray,
    jump_rate: float = 0.2,
) -> List[Individual]:
    """Phản chiếu một số cá thể để phun đa dạng vào quần thể."""
    X_matrix = np.array([ind.X for ind in population])
    pop_min = X_matrix.min(axis=0)
    pop_max = X_matrix.max(axis=0)

    reflected_x = []
    for ind in population:
        if random.random() < jump_rate:
            use_dynamic = random.random() < 0.5
            x_reflected = (pop_min + pop_max - ind.X) if use_dynamic else (xl + xu - ind.X)
            reflected_x.append(np.clip(x_reflected, xl, xu))

    if not reflected_x:
        return []

    x_batch = np.array(reflected_x)
    f_batch = problem.evaluate(x_batch)

    obl_inds = [_make_evaluated_individual(x_batch[i], f_batch[i]) for i in range(len(reflected_x))]
    for ind in obl_inds:
        ind.creation_mode = CreationMode.OBL

    return obl_inds


def tournament_selection(population: List[Individual]) -> Individual:
    """Chọn cá thể tốt hơn từ hai ứng viên ngẫu nhiên."""
    p1, p2 = random.sample(population, 2)
    if p1.rank != p2.rank:
        return p1 if p1.rank < p2.rank else p2
    return p1 if p1.crowding_dist >= p2.crowding_dist else p2