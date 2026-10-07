"""Paket UI Waste Anomaly Detection — PySide6 (rebuild v2.6.0).

UI lama (14 mixin Tkinter, 2000+ baris god-object) diganti arsitektur
view+signal: lihat ui/app.py (MainWindow) dan ui/state.py (AppContext).
Kontrak publik lama yang tetap: ui.shared (APP_DIR, app_dir,
bundle_res_dir, _apply_filters, fmt_id).

v2.13.8 (gel-C): __getattr__/__all__ lazy-export DIHAPUS — nol konsumen
in-repo (ui_app.py & semua test mengimpor submodul langsung:
``from ui.app import main``); import eksternal harus memakai submodul.
"""
