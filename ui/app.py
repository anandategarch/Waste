"""ui/app.py — komposisi class utama + entry point.

WasteAnomalyApp = 15 mixin (infrastruktur + 14 tab) + tk.Tk. Metode
dipindah VERBATIM dari ui_app.py lama (3.2k baris god-object) — lihat
ui/shared.py untuk konstanta & registry font. v2.5.0 menambah 4 mixin
tab analisa baru (Temporal, Money, Quality, Period) + 1 ekstensi Compare.
"""

from __future__ import annotations

import tkinter as tk

from waste_anomaly.logging_setup import install_tk_exception_hook, setup_logging

from .base import AppBase
from .tab_compare import CompareTabMixin
from .tab_config import ConfigTabMixin
from .tab_dashboard import DashboardTabMixin
from .tab_help import HelpTabMixin
from .tab_money import MoneyTabMixin
from .tab_period import PeriodTabMixin
from .tab_quality import QualityTabMixin
from .tab_quadrant import QuadrantTabMixin
from .tab_rate import RateLeagueTabMixin
from .tab_result import ResultTabMixin
from .tab_run import RunTabMixin
from .tab_summary import SummaryTabMixin
from .tab_temporal import TemporalTabMixin
from .tab_viz import VizTabMixin


class WasteAnomalyApp(
    AppBase,
    DashboardTabMixin,
    TemporalTabMixin,
    MoneyTabMixin,
    CompareTabMixin,
    QuadrantTabMixin,
    RateLeagueTabMixin,
    ResultTabMixin,
    VizTabMixin,
    QualityTabMixin,
    PeriodTabMixin,
    SummaryTabMixin,
    RunTabMixin,
    ConfigTabMixin,
    HelpTabMixin,
    tk.Tk,
):
    """Aplikasi utama — komposisi 15 modul mixin (14 tab + infrastruktur).

    Menambah tab baru = buat file mixin baru + daftar di sini (SATU tempat,
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
