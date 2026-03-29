"""Backward-compatible settings import path.

Prefer importing from server.app.core.settings.
"""

from .core.settings import AppSettings, get_settings

