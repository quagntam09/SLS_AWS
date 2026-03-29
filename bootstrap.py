from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT_CANDIDATES = (
    REPO_ROOT / "NSGA2IS-SLS",
    REPO_ROOT,
)

for candidate in PACKAGE_ROOT_CANDIDATES:
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from server.app.main import handler  # noqa: E402