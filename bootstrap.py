from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent / "NSGA2IS-SLS"
PROJECT_ROOT_STR = str(PROJECT_ROOT)
SERVER_ROOT_STR = str(PROJECT_ROOT / "server")

if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)

if SERVER_ROOT_STR not in sys.path:
    sys.path.insert(0, SERVER_ROOT_STR)

from server.app.main import handler  # noqa: E402