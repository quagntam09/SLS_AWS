"""
Sắp xếp Pareto và chọn lọc quần thể theo chuẩn NSGA-II.
"""

from __future__ import annotations

from typing import List

import numpy as np
from scipy.spatial.distance import cdist

from .core import Individual


def fast_non_dominated_sort(population: List[Individual]) -> List[List[Individual]]:
    """Phân chia quần thể thành các Pareto front bằng vector hoá O(n²·m)."""
    if not population:
        return []

    F = np.array([ind.F for ind in population])
    n = len(population)

    leq = (F[:, None, :] <= F[None, :, :]).all(axis=2)
    lt = (F[:, None, :] < F[None, :, :]).any(axis=2)
    dominates = leq & lt

    domination_count = dominates.sum(axis=0).astype(int)
    dominated_by = [np.where(dominates[i])[0].tolist() for i in range(n)]

    current_front_indices = np.where(domination_count == 0)[0].tolist()
    if not current_front_indices:
        return []

    fronts: List[List[Individual]] = []
    rank = 1

    while current_front_indices:
        for idx in current_front_indices:
            population[idx].rank = rank
        fronts.append([population[idx] for idx in current_front_indices])

        next_front_indices = []
        for p in current_front_indices:
            for q in dominated_by[p]:
                domination_count[q] -= 1
                if domination_count[q] == 0:
                    next_front_indices.append(q)

        current_front_indices = next_front_indices
        rank += 1

    return fronts


def calculate_crowding_distance(front: List[Individual], n_obj: int) -> None:
    """Gán khoảng cách crowding distance cho mọi cá thể trong một Pareto front."""
    n = len(front)
    if n == 0:
        return

    for ind in front:
        ind.crowding_dist = 0.0

    for m in range(n_obj):
        front.sort(key=lambda ind: ind.F[m])
        front[0].crowding_dist = float("inf")
        front[-1].crowding_dist = float("inf")

        f_range = front[-1].F[m] - front[0].F[m]
        if f_range == 0.0:
            continue

        for i in range(1, n - 1):
            if front[i].crowding_dist < float("inf"):
                front[i].crowding_dist += (front[i + 1].F[m] - front[i - 1].F[m]) / f_range


def remove_duplicates(population: List[Individual], epsilon: float = 1e-5) -> List[Individual]:
    """Loại bỏ cá thể gần trùng nhau trong không gian mục tiêu."""
    if not population:
        return population

    F = np.array([ind.F for ind in population])
    dists = cdist(F, F)
    is_dup = np.zeros(len(population), dtype=bool)

    for i in range(len(population)):
        if is_dup[i]:
            continue
        duplicates_of_i = np.where(dists[i, i + 1 :] < epsilon)[0] + (i + 1)
        is_dup[duplicates_of_i] = True

    return [ind for ind, dup in zip(population, is_dup) if not dup]


def environmental_selection(
    combined_pop: List[Individual],
    target_size: int,
    n_obj: int,
) -> List[Individual]:
    """Chọn target_size cá thể tốt nhất từ pool cha + con lai."""
    fronts = fast_non_dominated_sort(combined_pop)
    new_pop: List[Individual] = []

    for front in fronts:
        calculate_crowding_distance(front, n_obj)
        slots_left = target_size - len(new_pop)

        if len(front) <= slots_left:
            new_pop.extend(front)
        else:
            front.sort(key=lambda ind: ind.crowding_dist, reverse=True)
            new_pop.extend(front[:slots_left])
            break

    new_pop.sort(key=lambda ind: (ind.rank, -ind.crowding_dist))
    return new_pop