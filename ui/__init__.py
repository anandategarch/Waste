"""Paket UI Waste Anomaly Detection — PySide6 (rebuild v2.6.0).

UI lama (14 mixin Tkinter, 2000+ baris god-object) diganti arsitektur
view+signal: lihat ui/app.py (MainWindow) dan ui/state.py (AppContext).
Kontrak publik lama yang tetap: ui.shared (APP_DIR, app_dir,
bundle_res_dir, _apply_filters, fmt_id).
"""
from __future__ import annotations

__all__ = ["main", "MainWindow", "AppContext", "APP_VERSION", "APP_TITLE"]


def __getattr__(name: str):
    # Lazy import supaya `import ui` ringan (test struktur tanpa QApplication)
    if name in ("main", "MainWindow"):
        from . import app as _app
        return getattr(_app, name)
    if name == "AppContext":
        from .state import AppContext as _AppContext
        return _AppContext
    if name in ("APP_VERSION", "APP_TITLE"):
        from . import shared as _shared
        return getattr(_shared, name)
    raise AttributeError(f"module 'ui' has no attribute {name!r}")
