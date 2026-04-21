"""Compatibility bridge for legacy nsga2_improved imports.

The algorithm package was renamed/moved to OADE-NSGA-II (folder name contains a
hyphen, so it cannot be imported with a normal Python dotted path). This module
loads it dynamically and exposes the old symbols used by application code.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ALGO_DIR = Path(__file__).resolve().parents[1] / "OADE-NSGA-II"
_PACKAGE_NAME = "server._oade_nsga_ii"


def _load_oade_package():
    existing = sys.modules.get(_PACKAGE_NAME)
    if existing is not None:
        return existing

    init_file = _ALGO_DIR / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        _PACKAGE_NAME,
        init_file,
        submodule_search_locations=[str(_ALGO_DIR)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load algorithm package from {_ALGO_DIR}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[_PACKAGE_NAME] = module
    spec.loader.exec_module(module)
    return module


_pkg = _load_oade_package()

NSGA2ImprovedSmart = _pkg.OADE_NSGAII
OADE_NSGAII = _pkg.OADE_NSGAII
ProblemWrapper = _pkg.ProblemWrapper
Individual = _pkg.Individual
CreationMode = _pkg.CreationMode

__all__ = [
    "NSGA2ImprovedSmart",
    "OADE_NSGAII",
    "ProblemWrapper",
    "Individual",
    "CreationMode",
]
