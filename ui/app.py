"""ui/app.py — komposisi class utama + entry point.

WasteAnomalyApp = 11 mixin (infrastruktur + 10 tab) + tk.Tk. Metode
dipindah VERBATIM dari ui_app.py lama (3.2k baris god-object) — lihat
ui/shared.py untuk konstanta & registry font.
"""

from __future__ import annotations

import tkinter as tk

from waste_anomaly.logging_setup import install_tk_exception_hook, setup_logging

from .base import AppBase
from .tab_compare import CompareTabMixin
from .tab_config import ConfigTabMixin
from .tab_dashboard import DashboardTabMixin
from .tab_help import HelpTabMixin
from .tab_quadrant import QuadrantTabMixin
from .tab_rate import RateLeagueTabMixin
from .tab_result import ResultTabMixin
from .tab_run import RunTabMixin
from .tab_summary import SummaryTabMixin
from .tab_viz import VizTabMixin


class WasteAnomalyApp(
    AppBase,
    DashboardTabMixin,
    CompareTabMixin,
    QuadrantTabMixin,
    RateLeagueTabMixin,
    ResultTabMixin,
    VizTabMixin,
    SummaryTabMixin,
    RunTabMixin,
    ConfigTabMixin,
    HelpTabMixin,
    tk.Tk,
):
    """Aplikasi utama — komposisi 11 modul mixin (10 tab + infrastruktur).

    Menambah tab ke-11 = buat file mixin baru + daftar di sini (SATU tempat,
    dulu 5+ situs tersebar di god-object).
    """


def main():
    # F11 (v2.4.0): logging rotating-file aktif SEBELUM app dibangun —
    # exception selama startup pun tercatat ke logs/waste_anomaly.log.
    log_path = setup_logging()
    app = WasteAnomalyApp()
    install_tk_exception_hook(app)
    if log_path:
        app.log(f"File log: {log_path}")
    app.mainloop()
